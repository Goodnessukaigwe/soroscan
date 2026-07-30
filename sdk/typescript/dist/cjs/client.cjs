"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Paginator = exports.SoroScanClient = exports.SoroScanError = void 0;
// ─────────────────────────────────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────────────────────────────────
class SoroScanError extends Error {
    statusCode;
    code;
    details;
    constructor(statusCode, apiError) {
        super(apiError.message);
        this.name = "SoroScanError";
        this.statusCode = statusCode;
        this.code = apiError.code;
        this.details = apiError.details;
    }
}
exports.SoroScanError = SoroScanError;
// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function toQueryString(params) {
    const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null);
    if (entries.length === 0)
        return "";
    return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}
// ─────────────────────────────────────────────────────────────────────────────
// Client
// ─────────────────────────────────────────────────────────────────────────────
class SoroScanClient {
    #baseUrl;
    #apiKey;
    #timeoutMs;
    constructor(config) {
        if (!config.baseUrl) {
            throw new Error("SoroScanClient: baseUrl is required");
        }
        this.#baseUrl = config.baseUrl.replace(/\/$/, "");
        this.#apiKey = config.apiKey;
        this.#timeoutMs = config.timeoutMs ?? 30_000;
    }
    // ─── Core fetch ────────────────────────────────────────────────────────────
    async #request(method, path, options = {}) {
        const url = this.#baseUrl +
            path +
            (options.query ? toQueryString(options.query) : "");
        const headers = {
            "Content-Type": "application/json",
            Accept: "application/json",
        };
        if (this.#apiKey) {
            headers["Authorization"] = `Bearer ${this.#apiKey}`;
        }
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.#timeoutMs);
        let response;
        try {
            const init = {
                method,
                headers,
                signal: controller.signal,
            };
            if (options.body !== undefined) {
                init.body = JSON.stringify(options.body);
            }
            response = await fetch(url, init);
        }
        catch (err) {
            if (err instanceof Error && err.name === "AbortError") {
                throw new Error(`SoroScanClient: request timed out after ${this.#timeoutMs}ms`);
            }
            throw err;
        }
        finally {
            clearTimeout(timer);
        }
        // 204 No Content
        if (response.status === 204) {
            return undefined;
        }
        const json = await response.json().catch(() => null);
        if (!response.ok) {
            const apiError = json ?? {
                code: "UNKNOWN_ERROR",
                message: `HTTP ${response.status} ${response.statusText}`,
            };
            throw new SoroScanError(response.status, apiError);
        }
        return json;
    }
    // ─── Events ────────────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of contract events.
     *
     * @example
     * const result = await client.getEvents({ contractId: 'CCAAA...', first: 50 });
     * for (const event of result.items) { console.log(event.type, event.txHash); }
     */
    async getEvents(params = {}) {
        return this.#request("GET", "/v1/events", {
            query: params,
        });
    }
    /** Fetch events for several contracts with one indexed query. */
    async getEventsByContracts(params) {
        return this.#request("POST", "/v1/events/by-contracts", {
            body: params,
        });
    }
    /**
     * Submit an SC-38 structured event. The correlation ID makes retry handling
     * explicit: the contract rejects a repeated ID without publishing twice.
     */
    async recordStructuredEvent(params) {
        const response = await this.#request("POST", "/api/record/structured/", {
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
    async revokeStructuredEvent(params) {
        const response = await this.#request("POST", "/api/record/structured/revoke/", {
            body: {
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
    async getContracts(params = {}) {
        return this.#request("GET", "/v1/contracts", {
            query: params,
        });
    }
    /**
     * Retrieve details for a single contract by its address.
     *
     * @example
     * const contract = await client.getContract({ contractId: 'CCAAA...' });
     */
    async getContract(params) {
        const { contractId } = params;
        return this.#request("GET", `/v1/contracts/${encodeURIComponent(contractId)}`);
    }
    // ─── Transactions ──────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of transactions, optionally filtered by contract
     * or account.
     */
    async getTransactions(params = {}) {
        return this.#request("GET", "/v1/transactions", {
            query: params,
        });
    }
    /**
     * Retrieve a single transaction by hash.
     */
    async getTransaction(txHash) {
        return this.#request("GET", `/v1/transactions/${encodeURIComponent(txHash)}`);
    }
    // ─── Ledgers ───────────────────────────────────────────────────────────────
    /**
     * Retrieve a paginated list of ledgers.
     */
    async getLedgers(params = {}) {
        return this.#request("GET", "/v1/ledgers", {
            query: params,
        });
    }
    /**
     * Retrieve a single ledger by sequence number.
     */
    async getLedger(sequence) {
        return this.#request("GET", `/v1/ledgers/${sequence}`);
    }
    // ─── Accounts ──────────────────────────────────────────────────────────────
    /**
     * Retrieve account details including balances and contract interaction count.
     */
    async getAccount(params) {
        const { accountId } = params;
        return this.#request("GET", `/v1/accounts/${encodeURIComponent(accountId)}`);
    }
    // ─── Webhooks ──────────────────────────────────────────────────────────────
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
    async subscribeWebhook(params) {
        return this.#request("POST", "/v1/webhooks", { body: params });
    }
    /**
     * List all webhook subscriptions for the authenticated API key.
     */
    async listWebhooks() {
        return this.#request("GET", "/v1/webhooks");
    }
    /**
     * Retrieve a single webhook by ID.
     */
    async getWebhook(webhookId) {
        return this.#request("GET", `/v1/webhooks/${encodeURIComponent(webhookId)}`);
    }
    /**
     * Update a webhook (URL, triggers, or status).
     */
    async updateWebhook(webhookId, params) {
        return this.#request("PATCH", `/v1/webhooks/${encodeURIComponent(webhookId)}`, { body: params });
    }
    /**
     * Delete (unsubscribe) a webhook.
     */
    async deleteWebhook(webhookId) {
        return this.#request("DELETE", `/v1/webhooks/${encodeURIComponent(webhookId)}`);
    }
}
exports.SoroScanClient = SoroScanClient;
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
class Paginator {
    #fetcher;
    #baseParams;
    #pageSize;
    #currentPage = null;
    /** Cursor history: index 0 = before page 1, index n = endCursor of page n */
    #cursorHistory = [null];
    #currentIndex = 0;
    constructor(fetcher, baseParams = {}, pageSize = 20) {
        this.#fetcher = fetcher;
        this.#baseParams = baseParams;
        this.#pageSize = baseParams.first ?? pageSize;
    }
    // ─── State queries ──────────────────────────────────────────────────────────
    /**
     * Returns `true` if there is a next page available.
     * Always `true` before the first fetch (no data loaded yet).
     */
    hasNextPage() {
        if (this.#currentPage === null)
            return true;
        return this.#currentPage.pageInfo.hasNextPage;
    }
    /**
     * Returns `true` if there is a previous page available.
     */
    hasPreviousPage() {
        return this.#currentIndex > 1;
    }
    /**
     * The 1-indexed number of the page currently loaded, or `0` if no page has
     * been fetched yet.
     */
    get currentPageNumber() {
        return this.#currentIndex;
    }
    /**
     * The most recently fetched page, or `null` before the first fetch.
     */
    get currentPage() {
        return this.#currentPage;
    }
    // ─── Navigation ─────────────────────────────────────────────────────────────
    /**
     * Fetch the next page and return it.
     * Throws if there is no next page.
     */
    async nextPage() {
        if (this.#currentPage !== null && !this.#currentPage.pageInfo.hasNextPage) {
            throw new Error("Paginator: no next page available");
        }
        const afterCursor = this.#cursorHistory[this.#currentIndex] ?? undefined;
        const result = await this.#fetcher({
            ...this.#baseParams,
            first: this.#pageSize,
            after: afterCursor,
        });
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
    async previousPage() {
        if (!this.hasPreviousPage()) {
            throw new Error("Paginator: already on the first page");
        }
        this.#currentIndex -= 1;
        const afterCursor = this.#cursorHistory[this.#currentIndex - 1] ?? undefined;
        const result = await this.#fetcher({
            ...this.#baseParams,
            first: this.#pageSize,
            after: afterCursor,
        });
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
    async goToPage(pageNumber) {
        if (pageNumber < 1) {
            throw new Error("Paginator: pageNumber must be ≥ 1");
        }
        if (pageNumber <= this.#currentIndex) {
            // Navigate backwards using cached cursors
            this.#currentIndex = pageNumber;
            const afterCursor = this.#cursorHistory[this.#currentIndex - 1] ?? undefined;
            const result = await this.#fetcher({
                ...this.#baseParams,
                first: this.#pageSize,
                after: afterCursor,
            });
            this.#currentPage = result;
            return result;
        }
        // Navigate forward, fetching pages we haven't seen yet
        while (this.#currentIndex < pageNumber) {
            if (this.#currentPage !== null && !this.#currentPage.pageInfo.hasNextPage) {
                throw new Error(`Paginator: page ${pageNumber} does not exist (only ${this.#currentIndex} pages available)`);
            }
            await this.nextPage();
        }
        return this.#currentPage;
    }
    /**
     * Reset the paginator back to its initial state.
     * The next call to `nextPage()` will fetch page 1 again.
     */
    reset() {
        this.#currentPage = null;
        this.#cursorHistory = [null];
        this.#currentIndex = 0;
    }
}
exports.Paginator = Paginator;
//# sourceMappingURL=client.js.map