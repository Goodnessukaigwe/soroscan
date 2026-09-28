import { afterEach, describe, expect, it, vi } from "vitest";
import { SoroScanClient } from "../src/client.js";

const BASE_URL = "https://api.soroscan.io";

/**
 * A fetch stub that never settles on its own, exactly like a server that
 * accepts the connection but stalls before responding. It only rejects once the
 * request signal aborts, and rejects with `signal.reason` so the client sees
 * the same error a real fetch would raise.
 */
function stallingFetch() {
  return vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (signal?.aborted) {
          reject(signal.reason);
          return;
        }
        signal?.addEventListener("abort", () => reject(signal.reason));
      })
  );
}

describe("SoroScanClient request timeout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("aborts the request when the response exceeds timeoutMs", async () => {
    const fetchMock = stallingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const client = new SoroScanClient({
      baseUrl: BASE_URL,
      timeoutMs: 25,
      maxRetries: 0,
    });

    await expect(client.getEvents()).rejects.toThrow(
      "SoroScanClient: request timed out after 25ms"
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("passes an AbortSignal to fetch so the call is cancellable", async () => {
    const fetchMock = stallingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const client = new SoroScanClient({
      baseUrl: BASE_URL,
      timeoutMs: 25,
      maxRetries: 0,
    });

    await expect(client.getEvents()).rejects.toThrow("timed out");

    const signal = fetchMock.mock.calls[0]?.[1]?.signal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal?.aborted).toBe(true);
  });

  it("defaults to a 10_000ms timeout when timeoutMs is omitted", async () => {
    const fetchMock = stallingFetch();
    vi.stubGlobal("fetch", fetchMock);

    // Record the requested timeout, then hand back an already-aborted signal so
    // the assertion does not have to wait out the real 10s default.
    let requestedMs: number | undefined;
    vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
      requestedMs = ms;
      return AbortSignal.abort();
    });

    const client = new SoroScanClient({ baseUrl: BASE_URL, maxRetries: 0 });

    await expect(client.getEvents()).rejects.toThrow(
      "SoroScanClient: request timed out after 10000ms"
    );
    expect(requestedMs).toBe(10_000);
  });

  it("does not retry a timed-out request", async () => {
    const fetchMock = stallingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const client = new SoroScanClient({
      baseUrl: BASE_URL,
      timeoutMs: 25,
      maxRetries: 3,
    });

    await expect(client.getEvents()).rejects.toThrow("timed out after 25ms");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("propagates non-timeout network errors unchanged", async () => {
    const networkError = new TypeError("fetch failed");
    const fetchMock = vi.fn().mockRejectedValue(networkError);
    vi.stubGlobal("fetch", fetchMock);

    const client = new SoroScanClient({
      baseUrl: BASE_URL,
      timeoutMs: 25,
      maxRetries: 0,
    });

    await expect(client.getEvents()).rejects.toBe(networkError);
  });
});
