import { describe, it, expect } from "vitest";
import { verifySC36Payload } from "../src/features/sc36";

describe("SC-36 Payload Verifier", () => {
  it("should validate payloads correctly", () => {
    expect(verifySC36Payload({ version: "1.0", data: {} })).toBe(true);
    expect(verifySC36Payload({ version: "", data: {} })).toBe(false);
  });
});
