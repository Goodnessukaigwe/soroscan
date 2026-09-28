"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Star, FileCode2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  SortDirectionIndicator,
  type SortDirection,
} from "@/components/terminal/Table";
import { Button } from "@/components/terminal/Button";
import { EmptyState, EmptyStateIcon } from "@/components/ui/empty-state";
import type { Contract } from "@/components/ingest/contract-types";
import { useFavorites } from "@/lib/hooks/useFavorites";

export type ContractSortKey = "name" | "createdAt" | "lastEventTime";
export type SortableContract = Contract & { lastEventTime?: string };

interface ContractTableProps {
  contracts: SortableContract[];
  onDelete: (id: string) => void;
  onRegister: () => void;
  showFavoritesOnly?: boolean;
}

function parseTimestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDate(value: string | undefined): string {
  const timestamp = parseTimestamp(value);
  return timestamp === null ? "Never" : new Date(timestamp).toLocaleString();
}

export function sortContracts(
  contracts: SortableContract[],
  sortKey: ContractSortKey,
  sortDirection: SortDirection,
): SortableContract[] {
  return [...contracts].sort((a, b) => {
    // Keep equal values deterministic across reloads and duplicate fixtures.
    const tieBreak = a.id.localeCompare(b.id, "en", { numeric: true });

    if (sortKey === "name") {
      const comparison = (a.name ?? "").localeCompare(b.name ?? "", "en", {
        sensitivity: "base",
        numeric: true,
      });
      if (comparison === 0) return tieBreak;
      return sortDirection === "asc" ? comparison : -comparison;
    }

    const left = parseTimestamp(
      sortKey === "createdAt" ? a.createdAt : a.lastEventTime,
    );
    const right = parseTimestamp(
      sortKey === "createdAt" ? b.createdAt : b.lastEventTime,
    );

    // Missing or invalid timestamps always sort last, in either direction.
    // This is decided before the direction flip so descending cannot invert it.
    if (left === null && right === null) return tieBreak;
    if (left === null) return 1;
    if (right === null) return -1;

    const comparison = left - right;
    if (comparison === 0) return tieBreak;
    return sortDirection === "asc" ? comparison : -comparison;
  });
}

interface SortableHeadProps {
  label: string;
  sortKey: ContractSortKey;
  activeSortKey: ContractSortKey;
  direction: SortDirection;
  onToggle: (sortKey: ContractSortKey) => void;
}

function SortableHead({
  label,
  sortKey,
  activeSortKey,
  direction,
  onToggle,
}: SortableHeadProps) {
  const active = sortKey === activeSortKey;

  return (
    <TableHead aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        aria-label={`Sort by ${label}`}
        data-testid={`sort-${sortKey}`}
        className="inline-flex items-center gap-1 cursor-pointer select-none text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-terminal-green"
      >
        {label}
        <SortDirectionIndicator active={active} direction={direction} />
      </button>
    </TableHead>
  );
}

export function ContractTable({ contracts, onDelete, onRegister, showFavoritesOnly = false }: ContractTableProps) {
  const router = useRouter();
  const { isFavorite, toggleFavorite } = useFavorites();
  const [sortKey, setSortKey] = React.useState<ContractSortKey>("name");
  const [sortDirection, setSortDirection] = React.useState<SortDirection>("asc");

  const filteredContracts = showFavoritesOnly
    ? contracts.filter((contract) => isFavorite(contract.id))
    : contracts;
  const sortedContracts = sortContracts(filteredContracts, sortKey, sortDirection);

  const handleSort = (nextKey: ContractSortKey) => {
    if (nextKey === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection("asc");
  };

  const handleRowClick = (id: string) => {
    router.push(`/contracts/${id}`);
  };

  if (filteredContracts.length === 0) {
    return (
      <EmptyState
        variant="terminal"
        icon={
          <EmptyStateIcon>
            <FileCode2 className="h-8 w-8 text-terminal-green" />
          </EmptyStateIcon>
        }
        title="No contracts found"
        description="You are not tracking any contracts yet. Register a contract to begin."
        action={{
          label: "Register Contract",
          onClick: onRegister,
          terminalVariant: "primary",
        }}
      />
    );
  }

  return (
    <>
      {/* ── Mobile card view (< 640px) ── */}
      <div className="flex flex-col gap-3 sm:hidden" data-testid="contract-mobile-list">
        {sortedContracts.map((contract) => (
          <div
            key={contract.id}
            onClick={() => handleRowClick(contract.id)}
            className="cursor-pointer border border-terminal-green/20 bg-terminal-green/5 p-4 flex flex-col gap-3"
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="text-xs text-terminal-cyan uppercase mb-1">Contract ID</div>
                <div className="font-mono text-terminal-cyan text-sm">
                  {contract.contractId.slice(0, 8)}...
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleFavorite(contract.id);
                  }}
                  className="focus:outline-none min-w-[44px] min-h-[44px] flex items-center justify-center"
                  aria-label={isFavorite(contract.id) ? "Remove from favorites" : "Add to favorites"}
                >
                  <Star
                    size={20}
                    className={
                      isFavorite(contract.id)
                        ? "fill-yellow-400 text-yellow-400"
                        : "text-terminal-gray hover:text-yellow-400"
                    }
                  />
                </button>
                <span
                  className={`inline-flex items-center gap-2 px-2 py-1 text-xs font-mono ${
                    contract.status === "active"
                      ? "text-terminal-green border border-terminal-green/30 bg-terminal-green/10"
                      : "text-terminal-gray border border-terminal-gray/30 bg-terminal-gray/10"
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      contract.status === "active"
                        ? "bg-terminal-green animate-pulse"
                        : "bg-terminal-gray"
                    }`}
                  />
                  {contract.status.toUpperCase()}
                </span>
              </div>
            </div>

            <div>
              <div className="text-xs text-terminal-cyan uppercase mb-1">Name</div>
              <div className="font-semibold text-sm">{contract.name}</div>
            </div>

            <div className="flex justify-between items-center">
              <div>
                <div className="text-xs text-terminal-cyan uppercase mb-1">Events</div>
                <div className="font-mono text-sm">{contract.eventCount.toLocaleString()}</div>
              </div>
              <Button
                variant="danger"
                size="sm"
                className="w-full sm:w-auto"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(contract.id);
                }}
              >
                Delete
              </Button>
            </div>

            {contract.tags && contract.tags.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {contract.tags.slice(0, 3).map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-2 py-0.5 bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30"
                  >
                    {tag}
                  </span>
                ))}
                {(contract.tags?.length ?? 0) > 3 && (
                  <span className="text-xs text-terminal-gray">
                    +{(contract.tags?.length ?? 0) - 3}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Desktop table view (≥ 640px) ── */}
      <div className="hidden sm:block" data-testid="contract-desktop-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead>Contract ID</TableHead>
              <SortableHead
                label="Name"
                sortKey="name"
                activeSortKey={sortKey}
                direction={sortDirection}
                onToggle={handleSort}
              />
              <TableHead>Status</TableHead>
              <TableHead>Events</TableHead>
              <TableHead>Tags</TableHead>
              <SortableHead
                label="Created"
                sortKey="createdAt"
                activeSortKey={sortKey}
                direction={sortDirection}
                onToggle={handleSort}
              />
              <SortableHead
                label="Last Event"
                sortKey="lastEventTime"
                activeSortKey={sortKey}
                direction={sortDirection}
                onToggle={handleSort}
              />
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedContracts.map((contract) => (
              <TableRow
                key={contract.id}
                onClick={() => handleRowClick(contract.id)}
                className="cursor-pointer"
              >
                <TableCell>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleFavorite(contract.id);
                    }}
                    className="focus:outline-none"
                  >
                    <Star
                      size={20}
                      className={
                        isFavorite(contract.id)
                          ? "fill-yellow-400 text-yellow-400"
                          : "text-terminal-gray hover:text-yellow-400"
                      }
                    />
                  </button>
                </TableCell>
                <TableCell className="font-mono text-terminal-cyan">
                  {contract.contractId.slice(0, 8)}...
                </TableCell>
                <TableCell className="font-semibold">{contract.name}</TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center gap-2 px-2 py-1 text-xs font-mono ${
                      contract.status === "active"
                        ? "text-terminal-green border border-terminal-green/30 bg-terminal-green/10"
                        : "text-terminal-gray border border-terminal-gray/30 bg-terminal-gray/10"
                    }`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${
                        contract.status === "active"
                          ? "bg-terminal-green animate-pulse"
                          : "bg-terminal-gray"
                      }`}
                    />
                    {contract.status.toUpperCase()}
                  </span>
                </TableCell>
                <TableCell className="font-mono">{contract.eventCount.toLocaleString()}</TableCell>
                <TableCell>
                  <div className="flex gap-1 flex-wrap">
                    {contract.tags?.slice(0, 3).map((tag) => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-0.5 bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30"
                      >
                        {tag}
                      </span>
                    ))}
                    {(contract.tags?.length ?? 0) > 3 && (
                      <span className="text-xs text-terminal-gray">
                        +{(contract.tags?.length ?? 0) - 3}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs text-terminal-gray">
                  {formatDate(contract.createdAt)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs text-terminal-gray">
                  {formatDate(contract.lastEventTime)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(contract.id);
                    }}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}