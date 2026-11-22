import { describe, it, expect } from "vitest";
import { parseSC20Event } from "../src/features/sc20";

describe("SC-20 Event Parser", () => {
  it("should parse raw RPC events correctly", () => {
    const raw = { contractId: "C123", topic: "draw", data: { winner: "G123" }, timestamp: 1700000000 };
    const parsed = parseSC20Event(raw);
    expect(parsed.contractId).toBe("C123");
    expect(parsed.topic).toBe("draw");
    expect(parsed.timestamp).toBe(1700000000);
  });
});
