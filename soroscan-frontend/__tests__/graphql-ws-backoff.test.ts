import {
  GRAPHQL_WS_RETRY_ATTEMPTS,
  GRAPHQL_WS_RETRY_INITIAL_MS,
  GRAPHQL_WS_RETRY_MAX_MS,
  getGraphqlWsReconnectionAttempts,
  graphqlWsRetryDelayMs,
  recordGraphqlWsRetryAttempt,
  resetGraphqlWsReconnectionAttempts,
  shouldRetryGraphqlWs,
} from "@/lib/graphql-ws-backoff";

describe("graphql-ws exponential backoff", () => {
  beforeEach(() => {
    resetGraphqlWsReconnectionAttempts();
  });

  it("uses a ~1s delay for the first retry", () => {
    expect(graphqlWsRetryDelayMs(0)).toBe(GRAPHQL_WS_RETRY_INITIAL_MS);
    expect(graphqlWsRetryDelayMs(0)).toBe(1_000);
  });

  it("doubles the delay on each subsequent retry", () => {
    expect(graphqlWsRetryDelayMs(1)).toBe(2_000);
    expect(graphqlWsRetryDelayMs(2)).toBe(4_000);
    expect(graphqlWsRetryDelayMs(3)).toBe(8_000);
    expect(graphqlWsRetryDelayMs(4)).toBe(16_000);
  });

  it("caps the delay at 30s", () => {
    expect(graphqlWsRetryDelayMs(5)).toBe(GRAPHQL_WS_RETRY_MAX_MS);
    expect(graphqlWsRetryDelayMs(9)).toBe(30_000);
    expect(graphqlWsRetryDelayMs(20)).toBe(30_000);
  });

  it("stops retrying after 10 attempts", () => {
    expect(GRAPHQL_WS_RETRY_ATTEMPTS).toBe(10);
    const delays = Array.from({ length: GRAPHQL_WS_RETRY_ATTEMPTS }, (_, i) =>
      graphqlWsRetryDelayMs(i),
    );
    expect(delays).toHaveLength(10);
    expect(delays[0]).toBe(1_000);
    expect(delays[delays.length - 1]).toBe(30_000);
  });

  it("retries after an interruption with the initial delay again", () => {
    recordGraphqlWsRetryAttempt(4);
    expect(getGraphqlWsReconnectionAttempts()).toBe(5);
    expect(shouldRetryGraphqlWs()).toBe(true);

    resetGraphqlWsReconnectionAttempts();
    expect(getGraphqlWsReconnectionAttempts()).toBe(0);
    expect(graphqlWsRetryDelayMs(0)).toBe(1_000);
    expect(shouldRetryGraphqlWs()).toBe(true);
  });
});
