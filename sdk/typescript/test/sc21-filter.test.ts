import { describe, it, expect } from "vitest";
import { filterSC21Events, SC21Event } from "../src/features/sc21";

describe("SC-21 Event Filter", () => {
  it("should filter events by topic correctly", () => {
    const events: SC21Event[] = [
      { contractId: "C1", topic: "transfer", payload: ["A", "B"] },
      { contractId: "C1", topic: "mint", payload: ["A"] },
    ];
    const filtered = filterSC21Events(events, "transfer");
    expect(filtered.length).toBe(1);
    expect(filtered[0].topic).toBe("transfer");
  });
});
