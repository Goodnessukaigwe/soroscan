import type { SoroScanClientConfig, SoroScanApiError, ContractEventTypeInfo, GetEventsParams, GetEventsResponse, GetEventsByContractsParams, GetEventsByContractsResponse, RecordStructuredEventParams, RecordStructuredEventResponse, RevokeStructuredEventParams, RevokeStructuredEventResponse, GetContractsParams, GetContractsResponse, GetContractParams, Contract, GetTransactionsParams, GetTransactionsResponse, GetLedgersParams, GetLedgersResponse, GetAccountParams, Account, SubscribeWebhookParams, UpdateWebhookParams, Webhook, WebhookListResponse, PaginatedResponse, RecordEventsBatchParams, RecordEventsBatchResponse } from "./types.js";
import { EventQueryBuilder, ContractQueryBuilder } from "./builder.js";
export declare class SoroScanError extends Error {
    readonly statusCode: number;
    readonly code: string;
    readonly details: Record<string, unknown> | undefined;
    constructor(statusCode: number, apiError: SoroScanApiError);
}
export declare class SoroScanClient {
    #private;
    constructor(config: SoroScanClientConfig);
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
    events(): EventQueryBuilder;
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
    contracts(): ContractQueryBuilder;
    /**
     * Retrieve a paginated list of contract events.
     *
     * @example
     * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
     * for (const event of result.items) { console.log(event.type, event.txHash); }
     */
    getEvents(params?: GetEventsParams): Promise<GetEventsResponse>;
    /** Fetch events for several contracts with one indexed query. */
    getEventsByContracts(params: GetEventsByContractsParams): Promise<GetEventsByContractsResponse>;
    /**
     * Submit an SC-38 structured event. The correlation ID makes retry handling
     * explicit: the contract rejects a repeated ID without publishing twice.
     */
    recordStructuredEvent(params: RecordStructuredEventParams): Promise<RecordStructuredEventResponse>;
    /**
     * Revoke a previously recorded SC-38 structured event (SC-42).
     *
     * Marks the on-chain structured event as revoked so off-chain consumers can
     * treat it as invalid, while preserving the original audit trail. Revocation
     * is permanent; a second attempt fails with AlreadyRevoked.
     *
     * @example
     * const result = await client.revokeStructuredEvent({
     *   correlationId: 'b'.repeat(64),
     * });
     */
    revokeStructuredEvent(params: RevokeStructuredEventParams): Promise<RevokeStructuredEventResponse>;
    /**
     * Retrieve a paginated list of deployed contracts.
     *
     * @example
     * const result = await client.getContracts({ type: 'token', verified: true });
     */
    getContracts(params?: GetContractsParams): Promise<GetContractsResponse>;
    /**
     * Retrieve details for a single contract by its address.
     *
     * @example
     * const contract = await client.getContract({ contractId: 'CCAAA...' });
     */
    getContract(params: GetContractParams): Promise<Contract>;
    /**
     * Get event types and their counts for a specific contract (SC-17).
     *
     * @example
     * const types = await client.getContractEventTypes('CCAAA...');
     * for (const t of types) {
     *   console.log(t.eventType, t.count);
     * }
     */
    getContractEventTypes(contractId: string): Promise<ContractEventTypeInfo[]>;
    /**
     * Retrieve a paginated list of transactions, optionally filtered by contract
     * or account.
     */
    getTransactions(params?: GetTransactionsParams): Promise<GetTransactionsResponse>;
    /**
     * Retrieve a single transaction by hash.
     */
    getTransaction(txHash: string): Promise<import("./types.js").Transaction>;
    /**
     * Retrieve a paginated list of ledgers.
     */
    getLedgers(params?: GetLedgersParams): Promise<GetLedgersResponse>;
    /**
     * Retrieve a single ledger by sequence number.
     */
    getLedger(sequence: number): Promise<import("./types.js").Ledger>;
    /**
     * Retrieve account details including balances and contract interaction count.
     */
    getAccount(params: GetAccountParams): Promise<Account>;
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
    recordEventsBatch(params: RecordEventsBatchParams): Promise<RecordEventsBatchResponse>;
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
    subscribeWebhook(params: SubscribeWebhookParams): Promise<Webhook>;
    /**
     * List all webhook subscriptions for the authenticated API key.
     */
    listWebhooks(): Promise<WebhookListResponse>;
    /**
     * Retrieve a single webhook by ID.
     */
    getWebhook(webhookId: string): Promise<Webhook>;
    /**
     * Update a webhook (URL, triggers, or status).
     */
    updateWebhook(webhookId: string, params: UpdateWebhookParams): Promise<Webhook>;
    /**
     * Delete (unsubscribe) a webhook.
     */
    deleteWebhook(webhookId: string): Promise<void>;
}
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
export declare class Paginator<T, P extends {
    first?: number;
    after?: string;
    before?: string;
}> {
    #private;
    constructor(fetcher: (params: P) => Promise<PaginatedResponse<T>>, baseParams?: P, pageSize?: number);
    /**
     * Returns `true` if there is a next page available.
     * Always `true` before the first fetch (no data loaded yet).
     */
    hasNextPage(): boolean;
    /**
     * Returns `true` if there is a previous page available.
     */
    hasPreviousPage(): boolean;
    /**
     * The 1-indexed number of the page currently loaded, or `0` if no page has
     * been fetched yet.
     */
    get currentPageNumber(): number;
    /**
     * The most recently fetched page, or `null` before the first fetch.
     */
    get currentPage(): PaginatedResponse<T> | null;
    /**
     * Fetch the next page and return it.
     * Throws if there is no next page.
     */
    nextPage(): Promise<PaginatedResponse<T>>;
    /**
     * Fetch the previous page and return it.
     * Throws if already on the first page.
     */
    previousPage(): Promise<PaginatedResponse<T>>;
    /**
     * Jump to a specific 1-indexed page number.
     *
     * Pages already visited are reached via the cached cursor history.
     * Pages beyond the current furthest-fetched page are fetched sequentially
     * until the target is reached.
     *
     * @param pageNumber - 1-indexed target page (must be ≥ 1)
     */
    goToPage(pageNumber: number): Promise<PaginatedResponse<T>>;
    /**
     * Reset the paginator back to its initial state.
     * The next call to `nextPage()` will fetch page 1 again.
     */
    reset(): void;
}
//# sourceMappingURL=client.d.ts.map