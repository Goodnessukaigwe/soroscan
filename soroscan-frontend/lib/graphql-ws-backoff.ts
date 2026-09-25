/** Max GraphQL WS reconnect attempts after a drop. */
export const GRAPHQL_WS_RETRY_ATTEMPTS = 10;

/** First retry wait in milliseconds (~1s). */
export const GRAPHQL_WS_RETRY_INITIAL_MS = 1_000;

/** Upper bound for exponential backoff. */
export const GRAPHQL_WS_RETRY_MAX_MS = 30_000;

/**
 * Exponential delay for graphql-ws `retryWait`.
 * `retries` is 0-based (first reconnect wait uses retries = 0).
 */
export function graphqlWsRetryDelayMs(retries: number): number {
  if (retries < 0) {
    return GRAPHQL_WS_RETRY_INITIAL_MS;
  }
  return Math.min(
    GRAPHQL_WS_RETRY_INITIAL_MS * 2 ** retries,
    GRAPHQL_WS_RETRY_MAX_MS,
  );
}

export function shouldRetryGraphqlWs(): boolean {
  return true;
}

/** Live reconnect attempt counter (reset on a successful connection). */
let reconnectionAttempts = 0;

export function getGraphqlWsReconnectionAttempts(): number {
  return reconnectionAttempts;
}

export function recordGraphqlWsRetryAttempt(retries: number): void {
  reconnectionAttempts = retries + 1;
}

export function resetGraphqlWsReconnectionAttempts(): void {
  reconnectionAttempts = 0;
}
