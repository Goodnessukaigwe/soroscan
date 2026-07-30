import type {
  SoroScanClientConfig,
  SoroScanApiError,
  ContractEvent,
  ContractEventTypeInfo,
  GetContractRecentEventsParams,
  GetEventsParams,
  GetEventsResponse,
  GetEventsByContractsParams,
  GetEventsByContractsResponse,
  RecordStructuredEventParams,
  RecordStructuredEventResponse,
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
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

// ─────────────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────────────

export class SoroScanClient {
  readonly #baseUrl: string;
  readonly #apiKey: string | undefined;
  readonly #timeoutMs: number;

  constructor(config: SoroScanClientConfig) {
    if (!config.baseUrl) {
      throw new Error("SoroScanClient: baseUrl is required");
    }
    this.#baseUrl = config.baseUrl.replace(/\/$/, "");
    this.#apiKey = config.apiKey;
    this.#timeoutMs = config.timeoutMs ?? 30_000;
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

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.#timeoutMs);

    let response: Response;
    try {
      const init: RequestInit = {
        method,
        headers,
        signal: controller.signal as RequestInit["signal"],
      };
      if (options.body !== undefined) {
        init.body = JSON.stringify(options.body);
      }
      response = await fetch(url, init);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`SoroScanClient: request timed out after ${this.#timeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    // 204 No Content
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

  // ─── Builder factories (SC-10) ────────────────────────────────────────────

  /**
   * Create a fluent event query builder (SC-10).
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
   * @example
   * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
   * for (const event of result.items) { console.log(event.type, event.txHash); }
   */
  async getEvents(params: GetEventsParams = {}): Promise<GetEventsResponse> {
    return this.#request<GetEventsResponse>("GET", "/v1/events", {
      query: params as Record<string, unknown>,
    });
  }

  /** Fetch events for several contracts with one indexed query. */
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
   * Get event types and their counts for a specific contract (SC-17).
   *
   * @example
   * const types = await client.getContractEventTypes('CCAAA...');
   * for (const t of types) {
   *   console.log(t.eventType, t.count);
   * }
   */
  async getContractEventTypes(
    contractId: string
  ): Promise<ContractEventTypeInfo[]> {
    return this.#request<ContractEventTypeInfo[]>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}/event-types`
    );
  }

  /**
   * Get the most recent events for a specific contract, newest first (SC-30).
   *
   * @example
   * const events = await client.getContractRecentEvents({
   *   contractId: 'CCAAA...',
   *   limit: 5,
   * });
   */
  async getContractRecentEvents(
    params: GetContractRecentEventsParams
  ): Promise<ContractEvent[]> {
    const { contractId, limit = 10 } = params;
    if (limit < 1 || limit > MAX_RECENT_EVENTS_LIMIT) {
      throw new Error(
        `getContractRecentEvents: limit must be between 1 and ${MAX_RECENT_EVENTS_LIMIT}`
      );
    }
    return this.#request<ContractEvent[]>(
      "GET",
      `/v1/contracts/${encodeURIComponent(contractId)}/recent-events`,
      { query: { limit } }
    );
  }

  // ─── Transactions ──────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of transactions, optionally filtered by contract
   * or account.
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
   */
  async getTransaction(
    txHash: string
  ): Promise<import("./types.js").Transaction> {
    return this.#request("GET", `/v1/transactions/${encodeURIComponent(txHash)}`);
  }

  // ─── Ledgers ───────────────────────────────────────────────────────────────

  /**
   * Retrieve a paginated list of ledgers.
   */
  async getLedgers(params: GetLedgersParams = {}): Promise<GetLedgersResponse> {
    return this.#request<GetLedgersResponse>("GET", "/v1/ledgers", {
      query: params as Record<string, unknown>,
    });
  }

  /**
   * Retrieve a single ledger by sequence number.
   */
  async getLedger(sequence: number): Promise<import("./types.js").Ledger> {
    return this.#request("GET", `/v1/ledgers/${sequence}`);
  }

  // ─── Accounts ──────────────────────────────────────────────────────────────

  /**
   * Retrieve account details including balances and contract interaction count.
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
   * Create a new webhook subscription.
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
   */
  async listWebhooks(): Promise<WebhookListResponse> {
    return this.#request<WebhookListResponse>("GET", "/v1/webhooks");
  }

  /**
   * Retrieve a single webhook by ID.
   */
  async getWebhook(webhookId: string): Promise<Webhook> {
    return this.#request<Webhook>(
      "GET",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }

  /**
   * Update a webhook (URL, triggers, or status).
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
   */
  async deleteWebhook(webhookId: string): Promise<void> {
    return this.#request<void>(
      "DELETE",
      `/v1/webhooks/${encodeURIComponent(webhookId)}`
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pagination helpers — issue #483
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
