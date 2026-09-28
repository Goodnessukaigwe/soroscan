import type {
  SoroScanClientConfig,
  SoroScanApiError,
  ContractHealth,
  GetEventsParams,
  GetEventsResponse,
  GetEventsByContractsParams,
  GetEventsByContractsResponse,
  RecordStructuredEventParams,
  RecordStructuredEventResponse,
  RecordTaggedEventParams,
  RecordTaggedEventResponse,
  GetContractsParams,
  GetContractsResponse,
  GetContractParams,
  Contract,
  GetTransactionsParams,
  GetTransactionsResponse,
  GetLedgersParams,
  GetLedgersResponse,
  GetAccountParams,
  Account,
  SubscribeWebhookParams,
  UpdateWebhookParams,
  Webhook,
  WebhookListResponse,
  PaginatedResponse,
  RecordEventsBatchParams,
  RecordEventsBatchResponse,
  IndexerStats,
  ContractStatus,
  AddIndexerParams,
  AddIndexerResponse,
  GetAdminResponse,
  IsIndexerResponse,
} from "./types.js";
import { MAX_RECENT_EVENTS_LIMIT } from "./types.js";
import { EventQueryBuilder, ContractQueryBuilder } from "./builder.js";

// ─────────────────────────────────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────────────────────────────────

export class SoroScanError extends Error {
  readonly statusCode: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(statusCode: number, apiError: SoroScanApiError) {
    super(apiError.message);
    this.name = "SoroScanError";
    this.statusCode = statusCode;
    this.code = apiError.code;
    this.details = apiError.details;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function toQueryString(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null
  );
  if (entries.length === 0) return "";
  const queryParts = entries.map(([key, value]) => 
    `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`
  );
  return "?" + queryParts.join("&");
}

/**
 * True for errors raised when a request signal aborts, whether via an explicit
 * AbortController (name "AbortError") or AbortSignal.timeout (name
 * "TimeoutError"). Duck-typed on `name` because DOMException is not a reliable
 * `instanceof Error` across every runtime.
 */
function isAbortError(err: unknown): boolean {
  if (typeof err !== "object" || err === null || !("name" in err)) {
    return false;
  }
  const { name } = err as { name: unknown };
  return name === "AbortError" || name === "TimeoutError";
}

// ─────────────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────────────

export class SoroScanClient {
  readonly #baseUrl: string;
  readonly #apiKey: string | undefined;
  readonly #timeoutMs: number;
  readonly #maxRetries: number;
  readonly #initialDelayMs: number;
  readonly #maxDelayMs: number;

  constructor(config: SoroScanClientConfig) {
    if (!config.baseUrl) {
      throw new Error("SoroScanClient: baseUrl is required");
    }
    this.#baseUrl = config.baseUrl.replace(/\/$/, "");
    this.#apiKey = config.apiKey;
    this.#timeoutMs = config.timeoutMs ?? 10_000;
    this.#maxRetries = Math.max(0, Math.trunc(config.maxRetries ?? 3));
    this.#initialDelayMs = Math.max(0, config.initialDelayMs ?? 250);
    this.#maxDelayMs = Math.max(0, config.maxDelayMs ?? 10_000);
  }

  // ─── Core fetch ────────────────────────────────────────────────────────────
  async #request<T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    options: {
      query?: Record<string, unknown>;
      body?: unknown;
    } = {}
  ): Promise<T> {
    const url =
      this.#baseUrl +
      path +
      (options.query ? toQueryString(options.query) : "");
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.#apiKey) {
      headers["Authorization"] = `Bearer ${this.#apiKey}`;
    }

    const init: Omit<RequestInit, "signal"> = {
      method,
      headers,
    };
    if (options.body !== undefined) {
      init.body = JSON.stringify(options.body);
    }

    for (let attempt = 0; ; attempt += 1) {
      let response: Response;

      try {
        response = await fetch(url, {
          ...init,
          signal: AbortSignal.timeout(this.#timeoutMs),
        });
      } catch (err) {
        if (isAbortError(err)) {
          throw new Error(
            `SoroScanClient: request timed out after ${this.#timeoutMs}ms`
          );
        }
        throw err;
      }

      const retryable =
        response.status === 429 ||
        (response.status >= 500 && response.status <= 599);

      if (retryable && attempt < this.#maxRetries) {
        const exponentialCeiling = Math.min(
          this.#maxDelayMs,
          this.#initialDelayMs * 2 ** attempt
        );
        const delayMs = Math.random() * exponentialCeiling;
        if (delayMs > 0) {
          await new Promise<void>((resolve) => setTimeout(resolve, delayMs));
        }
        continue;
      }

      if (response.status === 204) {
        return undefined as T;
      }

      const json = await response.json().catch(() => null);

      if (!response.ok) {
        const apiError: SoroScanApiError = json ?? {
          code: "UNKNOWN_ERROR",
          message: `HTTP ${response.status} ${response.statusText}`,
        };
        throw new SoroScanError(response.status, apiError);
      }

      return json as T;
    }
  }

  // ─── Builder factories (SC-10) ────────────────────────────────────────────

  /**
   * Create a fluent event query builder (SC-10).
   *
   * @returns An `EventQueryBuilder` instance for constructing and executing
   *   filtered event queries with a chainable API.
   *
   * @example
   * const result = await client
   *   .events()
   *   .filterByContract("CCAAA...")
   *   .filterByEventType("transfer")
   *   .filterByLedgerRange(1_000, 2_000)
   *   .execute();
   */
  events(): EventQueryBuilder {
    return new EventQueryBuilder(this);
  }

  /**
   * Create a fluent contract query builder (SC-10).
   *
   * @returns A `ContractQueryBuilder` instance for constructing and executing
   *   filtered contract queries with a chainable API.
   *
   * @example
   * const result = await client
   *   .contracts()
   *   .filterByType("token")
   *   .filterByVerified(true)
   *   .search("my-token")
   *   .execute();
   */
  contracts(): ContractQueryBuilder {
    return new ContractQueryBuilder(this);
  }

  // ─── Events ────────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of contract events.
   *
   * @param params - Optional filter and pagination options such as `contractId`,
   *   `eventType`, `ledgerFrom`, `ledgerTo`, `first`, and `after`.
   * @returns A `GetEventsResponse` containing matched events and pagination info.
   *
   * @example
   * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
   * for (const event of result.items) { console.log(event.type, event.txHash); }
   */
  async getEvents(params: GetEventsParams = {}): Promise<GetEventsResponse> {
    return this.#request<GetEventsResponse>("GET", "/v1/events", {
      query: params as Record<string, unknown>,
    });
  }

  /** Fetch events for several contracts with one indexed query.
   *
   * @param params - Object containing an array of contract IDs and optional
   *   pagination / filter options.
   * @returns A response object containing matched events grouped by contract.
   */
  async getEventsByContracts(
    params: GetEventsByContractsParams
  ): Promise<GetEventsByContractsResponse> {
    return this.#request<GetEventsByContractsResponse>("POST", "/v1/events/by-contracts", {
      body: params,
    });
  }

  /**
   * Submit an SC-38 structured event. The correlation ID makes retry handling
   * explicit: the contract rejects a repeated ID without publishing twice.
   *
   * @param params - Structured event parameters including `contractId`,
   *   `eventType`, `payloadHash`, `schemaVersion`, and `correlationId`.
   * @returns Submission result with `status`, `txHash`, and `transactionStatus`.
   */
  async recordStructuredEvent(
    params: RecordStructuredEventParams
  ): Promise<RecordStructuredEventResponse> {
    const response = await this.#request<{
      status: "submitted" | "failed";
      tx_hash?: string;
      transaction_status: string;
      error?: string;
    }>("POST", "/api/record/structured/", {
      body: {
        contract_id: params.contractId,
        event_type: params.eventType,
        payload_hash: params.payloadHash,
        schema_version: params.schemaVersion,
        correlation_id: params.correlationId,
      },
    });
    return {
      status: response.status,
      txHash: response.tx_hash,
      transactionStatus: response.transaction_status,
      error: response.error,
    };
  }

  // ─── Contracts ─────────────────────────────────────────────────────────────


  /**
   * Retrieve a paginated list of deployed contracts.
   *
   * @param params - Optional filter and pagination options such as `type`,
   *   `verified`, `search`, `first`, and `after`.
   * @returns A `GetContractsResponse` containing matched contracts and pagination info.
   *
   * @example
   * const result = await client.getContracts({ type: 'token', verified: true });
   */
  async getContracts(
    params: GetContractsParams = {}
  ): Promise<GetContractsResponse> {
    return this.#request<GetContractsResponse>("GET", "/v1/contracts", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve details for a single contract by its address.
   *
   * @param params - Object containing the `contractId` (Stellar contract address).
   * @returns A `Contract` object with metadata, type, verification status, and stats.
   *
   * @example
   * const contract = await client.getContract({ contractId: 'CCAAA...' });
   */
  async getContract(params: GetContractParams): Promise<Contract> {
    const { contractId } = params;
    return this.#request<Contract>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}`
    );
  }

  /**
   * Get recent events for a specific contract (SC-16).
   *
   * @param contractId - The Stellar contract address to query.
   * @param limit - Maximum number of events to return (default: 100).
   * @returns An array of `ContractEvent` objects, ordered most-recent-first.
   *
   * @example
   * const events = await client.getContractEvents('CCAAA...', 20);
   * for (const event of events) {
   *   console.log(event.event_type, event.timestamp);
   * }
   */
  async getContractEvents(
    contractId: string,
    limit: number = 100
  ): Promise<import("./types.js").ContractEvent[]> {
    return this.#request<import("./types.js").ContractEvent[]>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}/events`,
      { query: { limit } }
    );
  }

  /**
   * Get health status for a tracked contract (SC-16).
   *
   * @param contractId - The Stellar contract address to query.
   * @returns A `ContractHealth` object with `status`, `lastChecked`, and
   *   `consecutiveFailures` metrics.
   *
   * @example
   * const health = await client.getContractHealth('CCAAA...');
   * console.log('Status:', health.status);
   * console.log('Consecutive failures:', health.consecutiveFailures);
   */
  async getContractHealth(contractId: string): Promise<ContractHealth> {
    return this.#request<ContractHealth>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}/health`
    );
  }

  // ─── Transactions ──────────────────────────────────────────────────────────

  /**
   * Submit an SC-24 tagged event.
   *
   * Tags are short producer-defined classification strings (e.g. `["defi",
   * "token"]`) that allow off-chain indexers to filter events without decoding
   * the full payload. At most 4 tags may be supplied per event.
   *
   * @param params - Tagged event parameters including `contractId`, `eventType`,
   *   `payloadHash`, and an optional `tags` array (max 4 items).
   * @returns A `RecordTaggedEventResponse` with `status`, `txHash`,
   *   `transactionStatus`, and the stored `tags`.
   *
   * @example
   * const result = await client.recordTaggedEvent({
   *   contractId: 'CCAAA...',
   *   eventType: 'transfer',
   *   payloadHash: 'a'.repeat(64),
   *   tags: ['defi', 'token'],
   * });
   */
  async recordTaggedEvent(
    params: RecordTaggedEventParams
  ): Promise<RecordTaggedEventResponse> {
    const response = await this.#request<{
      status: "submitted" | "failed";
      tx_hash?: string;
      transaction_status: string;
      error?: string;
      tags: string[];
    }>("POST", "/api/record/tagged/", {
      body: {
        contract_id: params.contractId,
        event_type: params.eventType,
        payload_hash: params.payloadHash,
        tags: params.tags ?? [],
      },
    });
    return {
      status: response.status,
      txHash: response.tx_hash,
      transactionStatus: response.transaction_status,
      error: response.error,
      tags: response.tags,
    };
  }

  /**
   * Retrieve a paginated list of transactions, optionally filtered by contract
   * or account.
   *
   * @param params - Optional filter and pagination options such as `contractId`,
   *   `accountId`, `first`, and `after`.
   * @returns A paginated response containing matching transactions.
   */
  async getTransactions(
    params: GetTransactionsParams = {}
  ): Promise<GetTransactionsResponse> {
    return this.#request<GetTransactionsResponse>("GET", "/v1/transactions", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve a single transaction by hash.
   *
   * @param txHash - The hex-encoded transaction hash.
   * @returns The matching `Transaction` object.
   */
  async getTransaction(
    txHash: string
  ): Promise<import("./types.js").Transaction> {
    return this.#request("GET", `/v1/transactions/${encodeURIComponent(txHash)}`);
  }

  // ─── Ledgers ───────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of ledgers.
   *
   * @param params - Optional pagination parameters such as `first` and `after`.
   * @returns A paginated response containing ledger summaries.
   */
  async getLedgers(params: GetLedgersParams = {}): Promise<GetLedgersResponse> {
    return this.#request<GetLedgersResponse>("GET", "/v1/ledgers", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve a single ledger by sequence number.
   *
   * @param sequence - The ledger sequence number.
   * @returns The matching `Ledger` object.
   */
  async getLedger(sequence: number): Promise<import("./types.js").Ledger> {
    return this.#request("GET", `/v1/ledgers/${sequence}`);
  }

  // ─── Accounts ──────────────────────────────────────────────────────────────

  /**
   * Retrieve account details including balances and contract interaction count.
   *
   * @param params - Object containing the `accountId` (Stellar public key).
   * @returns An `Account` object with balance and activity summary.
   */
  async getAccount(params: GetAccountParams): Promise<Account> {
    const { accountId } = params;
    return this.#request<Account>(
      "GET",
      `/v1/accounts/${encodeURIComponent(accountId)}`
    );
  }

  // ─── Webhooks ──────────────────────────────────────────────────────────────

  /**
   * Record multiple events in a single transaction (SC-29).
   * Maximum 25 events per batch.
   *
   * @param params - Object containing an `events` array of up to 25
   *   `{ contractId, eventType, payloadHash }` entries.
   * @returns A `RecordEventsBatchResponse` with `totalEvents` after the batch
   *   is recorded.
   *
   * @example
   * const result = await client.recordEventsBatch({
   *   events: [
   *     { contractId: 'CCAAA...', eventType: 'transfer', payloadHash: 'abc...' },
   *     { contractId: 'CCAAA...', eventType: 'swap', payloadHash: 'def...' },
   *   ],
   * });
   * console.log('Total events:', result.totalEvents);
   */
  async recordEventsBatch(
    params: RecordEventsBatchParams
  ): Promise<RecordEventsBatchResponse> {
    return this.#request<RecordEventsBatchResponse>(
      "POST",
      "/v1/record-events-batch",
      { body: params }
    );
  }

  /**
   * Check whether an address is an authorized indexer (SC-15).
   *
   * @param indexerAddress - The Stellar account address to check.
   * @returns An `IsIndexerResponse` indicating whether the address is registered
   *   and active as an indexer.
   */
  async isIndexer(indexerAddress: string): Promise<IsIndexerResponse> {
    return this.#request<IsIndexerResponse>("GET", "/api/ingest/indexers/check/", {
      query: { indexer_address: indexerAddress },
    });
  }

  /**
   * Return the current SoroScan contract admin address (SC-15).
   *
   * @returns A `GetAdminResponse` containing the admin's Stellar account address.
   */
  async getAdmin(): Promise<GetAdminResponse> {
    return this.#request<GetAdminResponse>("GET", "/api/ingest/contract/admin/");
  }

  /**
   * Authorize an indexer address on the SoroScan contract (SC-9).
   *
   * @param params - Object containing the `indexerAddress` (Stellar account
   *   address) to register as an authorized indexer.
   * @returns An `AddIndexerResponse` confirming the registration with the
   *   submitted transaction hash and status.
   *
   * @example
   * const result = await client.addIndexer({
   *   indexerAddress: 'GABC...',
   * });
   */
  async addIndexer(params: AddIndexerParams): Promise<AddIndexerResponse> {
    return this.#request<AddIndexerResponse>(
      "POST",
      "/api/ingest/indexers/add/",
      {
        body: {
          indexer_address: params.indexerAddress,
        },
      }
    );
  }

  /**
   * Get event recording statistics for a specific indexer (SC-13).
   *
   * @param indexer - The Stellar account address of the indexer to query.
   * @returns An `IndexerStats` object containing `eventsRecorded` and other
   *   activity counters for the specified indexer.
   *
   * @example
   * const stats = await client.getIndexerStats('GABC...');
   * console.log('Events recorded:', stats.eventsRecorded);
   */
  async getIndexerStats(indexer: string): Promise<IndexerStats> {
    return this.#request<IndexerStats>("GET", `/v1/indexer-stats/${indexer}`);
  }
  /**
   * Get the contract's current pause/health status (SC-28).
   *
   * @example
   * const status = await client.getContractStatus();
   * console.log('Paused:', status.paused);
   *
   * @returns A `ContractStatus` object indicating whether event recording is
   *   currently paused and other health metrics.
   */
  async getContractStatus(): Promise<ContractStatus> {
    return this.#request<ContractStatus>("GET", "/v1/contract-status");
  }

  /**
   * Create a new webhook subscription.
   *
   * @param params - Subscription options including `url`, `triggers` (event
   *   types to listen for), and an optional `contractId` to scope notifications.
   * @returns A `Webhook` object with the subscription ID, URL, triggers, and
   *   the HMAC `secret` used to verify delivery payloads.
   *
   * @example
   * const webhook = await client.subscribeWebhook({
   *   url: 'https://myapp.com/webhook',
   *   triggers: ['event.created'],
   *   contractId: 'CCAAA...',
   * });
   * console.log('Webhook secret:', webhook.secret);
   */
  async subscribeWebhook(params: SubscribeWebhookParams): Promise<Webhook> {
    return this.#request<Webhook>("POST", "/v1/webhooks", { body: params });
  }

  /**
   * List all webhook subscriptions for the authenticated API key.
   *
   * @returns A `WebhookListResponse` containing all registered webhook subscriptions.
   */
  async listWebhooks(): Promise<WebhookListResponse> {
    return this.#request<WebhookListResponse>("GET", "/v1/webhooks");
  }

  /**
   * Retrieve a single webhook by ID.
   *
   * @param webhookId - The unique webhook subscription identifier.
   * @returns The matching `Webhook` object.
   */
  async getWebhook(webhookId: string): Promise<Webhook> {
    return this.#request<Webhook>(
      "GET",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }

  /**
   * Update a webhook (URL, triggers, or status).
   *
   * @param webhookId - The unique webhook subscription identifier.
   * @param params - Fields to update: `url`, `triggers`, and/or `active` status.
   * @returns The updated `Webhook` object.
   */
  async updateWebhook(
    webhookId: string,
    params: UpdateWebhookParams
  ): Promise<Webhook> {
    return this.#request<Webhook>(
      "PATCH",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`,
      { body: params }
    );
  }

  /**
   * Delete (unsubscribe) a webhook.
   *
   * @param webhookId - The unique webhook subscription identifier to remove.
   * @returns `void` on success (HTTP 204 No Content).
   */
  async deleteWebhook(webhookId: string): Promise<void> {
    return this.#request<void>(
      "DELETE",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination helpers — issue #483 / #1283
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A stateful cursor-based paginator that wraps any SoroScan list method.
 *
 * Provides `hasNextPage()`, `nextPage()`, `previousPage()`, and `goToPage(n)`
 * so callers never have to manage cursors manually.
 *
 * @example
 * const paginator = new Paginator(
 *   (params) => client.getEvents(params),
 *   { contractId: 'CCAAA...', first: 20 }
 * );
 *
 * // Load first page
 * const page1 = await paginator.nextPage();
 *
 * if (paginator.hasNextPage()) {
 *   const page2 = await paginator.nextPage();
 * }
 *
 * // Jump to a specific page (1-indexed)
 * const page5 = await paginator.goToPage(5);
 *
 * // Go back
 * const page4 = await paginator.previousPage();
 */
export class Paginator<T, P extends { first?: number; after?: string; before?: string }> {
  readonly #fetcher: (params: P) => Promise<PaginatedResponse<T>>;
  readonly #baseParams: P;
  readonly #pageSize: number;

  #currentPage: PaginatedResponse<T> | null = null;
  /** Cursor history: index 0 = before page 1, index n = endCursor of page n */
  #cursorHistory: Array<string | null> = [null];
  #currentIndex = 0;

  constructor(
    fetcher: (params: P) => Promise<PaginatedResponse<T>>,
    baseParams: P = {} as P,
    pageSize = 20
  ) {
    this.#fetcher = fetcher;
    this.#baseParams = baseParams;
    this.#pageSize = baseParams.first ?? pageSize;
  }

  // ─── State queries ──────────────────────────────────────────────────────────

  /**
   * Returns `true` if there is a next page available.
   * Always `true` before the first fetch (no data loaded yet).
   */
  hasNextPage(): boolean {
    if (this.#currentPage === null) return true;
    return this.#currentPage.pageInfo.hasNextPage;
  }

  /**
   * Returns `true` if there is a previous page available.
   */
  hasPreviousPage(): boolean {
    return this.#currentIndex > 1;
  }

  /**
   * The 1-indexed number of the page currently loaded, or `0` if no page has
   * been fetched yet.
   */
  get currentPageNumber(): number {
    return this.#currentIndex;
  }

  /**
   * The most recently fetched page, or `null` before the first fetch.
   */
  get currentPage(): PaginatedResponse<T> | null {
    return this.#currentPage;
  }

  // ─── Navigation ─────────────────────────────────────────────────────────────

  /**
   * Fetch the next page and return it.
   * Throws if there is no next page.
   */
  async nextPage(): Promise<PaginatedResponse<T>> {
    if (this.#currentPage !== null && !this.#currentPage.pageInfo.hasNextPage) {
      throw new Error("Paginator: no next page available");
    }

    const afterCursor = this.#cursorHistory[this.#currentIndex] ?? undefined;
    const result = await this.#fetcher({
      ...this.#baseParams,
      first: this.#pageSize,
      after: afterCursor,
    } as P);

    this.#currentIndex += 1;
    // Record the end cursor for this page so we can navigate forward again
    this.#cursorHistory[this.#currentIndex] = result.pageInfo.endCursor;
    this.#currentPage = result;
    return result;
  }

  /**
   * Fetch the previous page and return it.
   * Throws if already on the first page.
   */
  async previousPage(): Promise<PaginatedResponse<T>> {
    if (!this.hasPreviousPage()) {
      throw new Error("Paginator: already on the first page");
    }

    this.#currentIndex -= 1;
    const afterCursor = this.#cursorHistory[this.#currentIndex - 1] ?? undefined;
    const result = await this.#fetcher({
      ...this.#baseParams,
      first: this.#pageSize,
      after: afterCursor,
    } as P);

    this.#currentPage = result;
    return result;
  }

  /**
   * Jump to a specific 1-indexed page number.
   *
   * Pages already visited are reached via the cached cursor history.
   * Pages beyond the current furthest-fetched page are fetched sequentially
   * until the target is reached.
   *
   * @param pageNumber - 1-indexed target page (must be ≥ 1)
   */
  async goToPage(pageNumber: number): Promise<PaginatedResponse<T>> {
    if (pageNumber < 1) {
      throw new Error("Paginator: pageNumber must be ≥ 1");
    }

    if (pageNumber <= this.#currentIndex) {
      // Navigate backwards using cached cursors
      this.#currentIndex = pageNumber;
      const afterCursor =
        this.#cursorHistory[this.#currentIndex - 1] ?? undefined;
      const result = await this.#fetcher({
        ...this.#baseParams,
        first: this.#pageSize,
        after: afterCursor,
      } as P);
      this.#currentPage = result;
      return result;
    }

    // Navigate forward, fetching pages we haven't seen yet
    while (this.#currentIndex < pageNumber) {
      if (this.#currentPage !== null && !this.#currentPage.pageInfo.hasNextPage) {
        throw new Error(
          `Paginator: page ${pageNumber} does not exist (only ${this.#currentIndex} pages available)`
        );
      }
      await this.nextPage();
    }

    return this.#currentPage!;
  }

  /**
   * Reset the paginator back to its initial state.
   * The next call to `nextPage()` will fetch page 1 again.
   */
  reset(): void {
    this.#currentPage = null;
    this.#cursorHistory = [null];
    this.#currentIndex = 0;
  }
}
