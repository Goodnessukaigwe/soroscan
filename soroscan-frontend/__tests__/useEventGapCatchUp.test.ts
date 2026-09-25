import { act, renderHook, waitFor } from "@testing-library/react";

import type { EventRecord } from "@/components/ingest/types";
import {
  prependRecoveredEvents,
  useEventGapCatchUp,
} from "@/src/hooks/useEventGapCatchUp";

function event(partial: Partial<EventRecord> & Pick<EventRecord, "id" | "ledger">): EventRecord {
  return {
    contractId: "C1",
    contractName: "Core",
    eventType: "swap",
    eventIndex: 0,
    timestamp: "2026-01-01T00:00:00Z",
    txHash: "tx",
    payload: {},
    ...partial,
  };
}

describe("prependRecoveredEvents", () => {
  it("prepends recovered events newest-first and skips duplicates", () => {
    const existing = [event({ id: "a", ledger: 10 }), event({ id: "b", ledger: 9 })];
    const recovered = [
      event({ id: "c", ledger: 11 }),
      event({ id: "a", ledger: 10 }),
      event({ id: "d", ledger: 12 }),
    ];

    const merged = prependRecoveredEvents(existing, recovered);
    expect(merged.map((item) => item.id)).toEqual(["d", "c", "a", "b"]);
  });
});

describe("useEventGapCatchUp", () => {
  const fetchCurrentLedger = jest.fn();
  const fetchEventsInRange = jest.fn();

  beforeEach(() => {
    fetchCurrentLedger.mockReset();
    fetchEventsInRange.mockReset();
  });

  it("does not catch up on the initial connected state", async () => {
    renderHook(() =>
      useEventGapCatchUp("C1", true, { fetchCurrentLedger, fetchEventsInRange }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchCurrentLedger).not.toHaveBeenCalled();
    expect(fetchEventsInRange).not.toHaveBeenCalled();
  });

  it("queries the ledger gap on a false -> true reconnect", async () => {
    fetchCurrentLedger.mockResolvedValue(120);
    fetchEventsInRange.mockResolvedValue([event({ id: "gap", ledger: 115 })]);

    const { result, rerender } = renderHook(
      ({ connected }: { connected: boolean }) =>
        useEventGapCatchUp("C1", connected, {
          fetchCurrentLedger,
          fetchEventsInRange,
        }),
      { initialProps: { connected: true } },
    );

    act(() => {
      result.current.recordReceivedEvent({ id: "live", ledger: 100 });
    });

    rerender({ connected: false });
    rerender({ connected: true });

    await waitFor(() => {
      expect(fetchCurrentLedger).toHaveBeenCalledWith("C1");
      expect(fetchEventsInRange).toHaveBeenCalledWith("C1", 100, 120);
    });

    await waitFor(() => {
      expect(result.current.recoveredEvents.map((item) => item.id)).toEqual(["gap"]);
      expect(result.current.lastRequestedRange).toEqual({
        fromLedger: 100,
        toLedger: 120,
      });
    });
  });

  it("skips recovery when there is no ledger gap", async () => {
    fetchCurrentLedger.mockResolvedValue(100);

    const { result, rerender } = renderHook(
      ({ connected }: { connected: boolean }) =>
        useEventGapCatchUp("C1", connected, {
          fetchCurrentLedger,
          fetchEventsInRange,
        }),
      { initialProps: { connected: true } },
    );

    act(() => {
      result.current.recordReceivedEvent({ id: "live", ledger: 100 });
    });

    rerender({ connected: false });
    rerender({ connected: true });

    await waitFor(() => {
      expect(fetchCurrentLedger).toHaveBeenCalled();
    });

    expect(fetchEventsInRange).not.toHaveBeenCalled();
    expect(result.current.recoveredEvents).toEqual([]);
  });

  it("does not insert recovered events that are already known", async () => {
    fetchCurrentLedger.mockResolvedValue(110);
    fetchEventsInRange.mockResolvedValue([
      event({ id: "live", ledger: 100 }),
      event({ id: "gap", ledger: 105 }),
    ]);

    const { result, rerender } = renderHook(
      ({ connected }: { connected: boolean }) =>
        useEventGapCatchUp("C1", connected, {
          fetchCurrentLedger,
          fetchEventsInRange,
        }),
      { initialProps: { connected: true } },
    );

    act(() => {
      result.current.recordReceivedEvent({ id: "live", ledger: 100 });
    });

    rerender({ connected: false });
    rerender({ connected: true });

    await waitFor(() => {
      expect(result.current.recoveredEvents.map((item) => item.id)).toEqual(["gap"]);
    });
  });

  it("updates the tracked ledger across disconnect/reconnect cycles", async () => {
    fetchCurrentLedger.mockResolvedValueOnce(110).mockResolvedValueOnce(130);
    fetchEventsInRange
      .mockResolvedValueOnce([event({ id: "g1", ledger: 105 })])
      .mockResolvedValueOnce([event({ id: "g2", ledger: 125 })]);

    const { result, rerender } = renderHook(
      ({ connected }: { connected: boolean }) =>
        useEventGapCatchUp("C1", connected, {
          fetchCurrentLedger,
          fetchEventsInRange,
        }),
      { initialProps: { connected: true } },
    );

    act(() => {
      result.current.recordReceivedEvent({ id: "live", ledger: 100 });
    });
    expect(result.current.lastReceivedLedger).toBe(100);

    rerender({ connected: false });
    rerender({ connected: true });

    await waitFor(() => {
      expect(result.current.lastReceivedLedger).toBe(105);
    });

    act(() => {
      result.current.recordReceivedEvent({ id: "later", ledger: 118 });
    });
    expect(result.current.lastReceivedLedger).toBe(118);

    rerender({ connected: false });
    rerender({ connected: true });

    await waitFor(() => {
      expect(fetchEventsInRange).toHaveBeenLastCalledWith("C1", 118, 130);
      expect(result.current.lastReceivedLedger).toBe(125);
    });
  });

  it("resets tracked state when contractId changes", async () => {
    fetchCurrentLedger.mockResolvedValue(200);

    const { result, rerender } = renderHook(
      ({ contractId, connected }: { contractId: string; connected: boolean }) =>
        useEventGapCatchUp(contractId, connected, {
          fetchCurrentLedger,
          fetchEventsInRange,
        }),
      { initialProps: { contractId: "C1", connected: true } },
    );

    act(() => {
      result.current.recordReceivedEvent({ id: "live", ledger: 50 });
    });
    expect(result.current.lastReceivedLedger).toBe(50);

    rerender({ contractId: "C2", connected: true });

    expect(result.current.lastReceivedLedger).toBeNull();
    expect(fetchEventsInRange).not.toHaveBeenCalled();
  });
});
