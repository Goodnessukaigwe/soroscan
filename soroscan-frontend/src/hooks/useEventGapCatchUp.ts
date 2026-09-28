"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchCurrentLedger as defaultFetchCurrentLedger,
  fetchEventsInLedgerRange as defaultFetchEventsInLedgerRange,
} from "@/components/ingest/graphql";
import type { EventRecord } from "@/components/ingest/types";

export interface GapCatchUpEventRef {
  id: string;
  ledger: number;
}

export interface UseEventGapCatchUpOptions {
  fetchCurrentLedger?: (contractId: string) => Promise<number | null>;
  fetchEventsInRange?: (
    contractId: string,
    fromLedger: number,
    toLedger: number,
  ) => Promise<EventRecord[]>;
}

/**
 * Prepend recovered events in Event Explorer order (newest ledger first)
 * without duplicating ids already in the list.
 */
export function prependRecoveredEvents(
  existing: EventRecord[],
  recovered: EventRecord[],
): EventRecord[] {
  const existingIds = new Set(existing.map((event) => event.id));
  const unique = recovered.filter((event) => !existingIds.has(event.id));
  unique.sort((a, b) => {
    if (b.ledger !== a.ledger) {
      return b.ledger - a.ledger;
    }
    return (b.eventIndex ?? 0) - (a.eventIndex ?? 0);
  });
  return [...unique, ...existing];
}

export function useEventGapCatchUp(
  contractId: string,
  isConnected: boolean,
  options: UseEventGapCatchUpOptions = {},
) {
  const fetchCurrentLedger =
    options.fetchCurrentLedger ?? defaultFetchCurrentLedger;
  const fetchEventsInRange =
    options.fetchEventsInRange ?? defaultFetchEventsInLedgerRange;

  const [recoveredEvents, setRecoveredEvents] = useState<EventRecord[]>([]);
  const [lastReceivedLedger, setLastReceivedLedger] = useState<number | null>(
    null,
  );
  const [lastRequestedRange, setLastRequestedRange] = useState<{
    fromLedger: number;
    toLedger: number;
  } | null>(null);

  const lastReceivedLedgerRef = useRef<number | null>(null);
  const knownIdsRef = useRef<Set<string>>(new Set());
  const prevConnectedRef = useRef<boolean | null>(null);
  const prevContractIdRef = useRef(contractId);

  const recordReceivedEvent = useCallback((event: GapCatchUpEventRef) => {
    knownIdsRef.current.add(event.id);
    const current = lastReceivedLedgerRef.current;
    if (current === null || event.ledger > current) {
      lastReceivedLedgerRef.current = event.ledger;
      setLastReceivedLedger(event.ledger);
    }
  }, []);

  useEffect(() => {
    if (prevContractIdRef.current !== contractId) {
      prevContractIdRef.current = contractId;
      lastReceivedLedgerRef.current = null;
      knownIdsRef.current = new Set();
      setRecoveredEvents([]);
      setLastRequestedRange(null);
      setLastReceivedLedger(null);
      prevConnectedRef.current = isConnected;
    }
  }, [contractId, isConnected]);

  useEffect(() => {
    if (prevConnectedRef.current === null) {
      prevConnectedRef.current = isConnected;
      return;
    }

    const wasConnected = prevConnectedRef.current;
    prevConnectedRef.current = isConnected;

    const reconnected = !wasConnected && isConnected;
    if (!reconnected || !contractId) {
      return;
    }

    const lastReceivedLedger = lastReceivedLedgerRef.current;
    if (lastReceivedLedger === null) {
      return;
    }

    let cancelled = false;

    const runCatchUp = async () => {
      const currentLedger = await fetchCurrentLedger(contractId);
      if (cancelled || currentLedger === null) {
        return;
      }

      if (currentLedger <= lastReceivedLedger) {
        return;
      }

      const fromLedger = lastReceivedLedger;
      const toLedger = currentLedger;
      setLastRequestedRange({ fromLedger, toLedger });

      const missing = await fetchEventsInRange(contractId, fromLedger, toLedger);
      if (cancelled) {
        return;
      }

      const unique = missing.filter((event) => !knownIdsRef.current.has(event.id));
      if (!unique.length) {
        return;
      }

      unique.forEach((event) => {
        knownIdsRef.current.add(event.id);
        const current = lastReceivedLedgerRef.current;
        if (current === null || event.ledger > current) {
          lastReceivedLedgerRef.current = event.ledger;
          setLastReceivedLedger(event.ledger);
        }
      });

      setRecoveredEvents(unique);
    };

    void runCatchUp();

    return () => {
      cancelled = true;
    };
  }, [contractId, fetchCurrentLedger, fetchEventsInRange, isConnected]);

  return {
    lastReceivedLedger,
    recoveredEvents,
    lastRequestedRange,
    recordReceivedEvent,
  };
}
