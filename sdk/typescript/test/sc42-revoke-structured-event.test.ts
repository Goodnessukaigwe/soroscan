import { afterEach, describe, expect, it, vi } from "vitest";
import { SoroScanClient } from "../src/client.js";

describe("revokeStructuredEvent() — SC-42", () => {
  afterEach(() => vi.restoreAllMocks());

  it("serializes the revocation payload and reports success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ status: "submitted", tx_hash: "def", transaction_status: "PENDING" }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io", apiKey: "key" });
    const result = await client.revokeStructuredEvent({
      correlationId: "b".repeat(64),
    });

    expect(result.status).toBe("submitted");
    expect(result.txHash).toBe("def");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.soroscan.io/api/record/structured/revoke/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      correlation_id: "b".repeat(64),
    });
  });

  it("surfaces a failed revocation (e.g. already revoked) without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "failed",
            error: "already revoked",
            transaction_status: "error",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io", apiKey: "key" });
    const result = await client.revokeStructuredEvent({
      correlationId: "b".repeat(64),
    });

    expect(result.status).toBe("failed");
    expect(result.error).toBe("already revoked");
  });
});
