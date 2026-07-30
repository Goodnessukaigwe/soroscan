import { afterEach, describe, expect, it, vi } from "vitest";
import { SoroScanClient } from "../src/client.js";

describe("retractStructuredEvent() — SC-37", () => {
  afterEach(() => vi.restoreAllMocks());

  it("serializes the retraction payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ status: "submitted", tx_hash: "abc", transaction_status: "PENDING" }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io", apiKey: "key" });
    const result = await client.retractStructuredEvent({
      correlationId: "b".repeat(64),
      reason: "reorg",
    });

    expect(result.status).toBe("submitted");
    expect(result.txHash).toBe("abc");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.soroscan.io/api/record/retract/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      correlation_id: "b".repeat(64),
      reason: "reorg",
    });
  });

  it("defaults the reason to 'unspecified' when omitted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ status: "submitted", tx_hash: "abc", transaction_status: "PENDING" }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io" });
    await client.retractStructuredEvent({ correlationId: "c".repeat(64) });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string).reason).toBe("unspecified");
  });

  it("surfaces a failed retraction (e.g. already retracted)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "failed",
            error: "already retracted",
            transaction_status: "FAILED",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io" });
    const result = await client.retractStructuredEvent({ correlationId: "d".repeat(64) });

    expect(result.status).toBe("failed");
    expect(result.error).toBe("already retracted");
  });
});
