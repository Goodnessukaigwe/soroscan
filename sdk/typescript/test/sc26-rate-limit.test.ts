import { describe, it, expect, vi, afterEach } from "vitest";
import { SoroScanClient, SoroScanError } from "../src/client.js";
import type { IndexerRateLimit, SetIndexerRateLimitResponse } from "../src/types.js";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      })
    )
  );
}

const BASE_URL = "https://api.soroscan.io";
const makeClient = () => new SoroScanClient({ baseUrl: BASE_URL, apiKey: "test-key" });

const SAMPLE_INDEXER = "GABC1111111111111111111111111111111111111111111111111111";

const MOCK_SET_RESPONSE: SetIndexerRateLimitResponse = {
  status: "submitted",
  txHash: "txratelimit001",
  transactionStatus: "pending",
  error: null,
};

const MOCK_LIMIT: IndexerRateLimit = {
  indexer: SAMPLE_INDEXER,
  maxEventsPerLedger: 100,
};

// ─────────────────────────────────────────────────────────────────────────────
// SC-26: setIndexerRateLimit / getIndexerRateLimit
// ─────────────────────────────────────────────────────────────────────────────

describe("setIndexerRateLimit() — SC-26", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts to /v1/indexers/rate-limit and returns response", async () => {
    mockFetch(MOCK_SET_RESPONSE, 202);
    const result = await makeClient().setIndexerRateLimit({
      indexer: SAMPLE_INDEXER,
      maxEventsPerLedger: 100,
    });

    expect(result.status).toBe("submitted");
    expect(result.txHash).toBe("txratelimit001");
    expect(result.error).toBeNull();

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toContain("/v1/indexers/rate-limit");
    expect(init.method).toBe("POST");
  });

  it("sends correct payload in request body", async () => {
    mockFetch(MOCK_SET_RESPONSE, 202);
    await makeClient().setIndexerRateLimit({
      indexer: SAMPLE_INDEXER,
      maxEventsPerLedger: 250,
    });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    const body = JSON.parse(init.body as string) as {
      indexer: string;
      maxEventsPerLedger: number;
    };
    expect(body.indexer).toBe(SAMPLE_INDEXER);
    expect(body.maxEventsPerLedger).toBe(250);
  });

  it("allows clearing a limit with maxEventsPerLedger: 0", async () => {
    mockFetch(MOCK_SET_RESPONSE, 202);
    await makeClient().setIndexerRateLimit({
      indexer: SAMPLE_INDEXER,
      maxEventsPerLedger: 0,
    });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    const body = JSON.parse(init.body as string) as { maxEventsPerLedger: number };
    expect(body.maxEventsPerLedger).toBe(0);
  });

  it("includes Authorization header", async () => {
    mockFetch(MOCK_SET_RESPONSE, 202);
    await makeClient().setIndexerRateLimit({
      indexer: SAMPLE_INDEXER,
      maxEventsPerLedger: 100,
    });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer test-key"
    );
  });

  it("throws SoroScanError on 400 validation error", async () => {
    mockFetch({ code: "INVALID_INDEXER", message: "Invalid indexer address" }, 400);
    await expect(
      makeClient().setIndexerRateLimit({
        indexer: "not-an-address",
        maxEventsPerLedger: 100,
      })
    ).rejects.toMatchObject({
      name: "SoroScanError",
      statusCode: 400,
      code: "INVALID_INDEXER",
    });
  });

  it("throws SoroScanError on 403 forbidden (non-admin)", async () => {
    mockFetch({ code: "FORBIDDEN", message: "Admin privileges required" }, 403);
    await expect(
      makeClient().setIndexerRateLimit({
        indexer: SAMPLE_INDEXER,
        maxEventsPerLedger: 100,
      })
    ).rejects.toMatchObject({ statusCode: 403 });
  });

  it("throws SoroScanError on 500 server error", async () => {
    mockFetch({ code: "SERVER_ERROR", message: "Internal error" }, 500);
    await expect(
      makeClient().setIndexerRateLimit({
        indexer: SAMPLE_INDEXER,
        maxEventsPerLedger: 100,
      })
    ).rejects.toBeInstanceOf(SoroScanError);
  });
});

describe("getIndexerRateLimit() — SC-26", () => {
  afterEach(() => vi.restoreAllMocks());

  it("gets /v1/indexers/{indexer}/rate-limit and returns the limit", async () => {
    mockFetch(MOCK_LIMIT, 200);
    const result = await makeClient().getIndexerRateLimit(SAMPLE_INDEXER);

    expect(result.indexer).toBe(SAMPLE_INDEXER);
    expect(result.maxEventsPerLedger).toBe(100);

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toContain(`/v1/indexers/${SAMPLE_INDEXER}/rate-limit`);
    expect(init.method).toBe("GET");
  });

  it("returns null maxEventsPerLedger for an unrestricted indexer", async () => {
    mockFetch({ indexer: SAMPLE_INDEXER, maxEventsPerLedger: null }, 200);
    const result = await makeClient().getIndexerRateLimit(SAMPLE_INDEXER);
    expect(result.maxEventsPerLedger).toBeNull();
  });

  it("URL-encodes the indexer address", async () => {
    mockFetch(MOCK_LIMIT, 200);
    await makeClient().getIndexerRateLimit(SAMPLE_INDEXER);

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain(encodeURIComponent(SAMPLE_INDEXER));
  });

  it("throws SoroScanError on 404 unknown indexer", async () => {
    mockFetch({ code: "NOT_FOUND", message: "Indexer not found" }, 404);
    await expect(makeClient().getIndexerRateLimit(SAMPLE_INDEXER)).rejects.toMatchObject({
      statusCode: 404,
    });
  });
});
