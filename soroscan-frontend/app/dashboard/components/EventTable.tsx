"use client";

import { useEffect, useRef, useState } from "react";
import type { InputHTMLAttributes, KeyboardEvent } from "react";
import { Search, Inbox } from "lucide-react";
import { EmptyState, EmptyStateIcon } from "@/components/ui/empty-state";
import { EventTableSkeleton } from "@/components/ui/skeletons";
import { formatDateTime, shortHash } from "@/components/ingest/formatters";
import type { EventRecord } from "@/components/ingest/types";
import styles from "@/components/ingest/ingest-terminal.module.css";
import toolbarStyles from "./BulkActionsToolbar.module.css";

interface EventTableProps {
  events: EventRecord[];
  loading: boolean;
  onEventClick: (event: EventRecord) => void;
  eventTags?: Record<string, string[]>;
  tagSuggestions?: string[];
  onAddTag?: (eventId: string, tag: string) => void;
  onRemoveTag?: (eventId: string, tag: string) => void;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  showTags?: boolean;
  selectedIds?: Set<string>;
  onToggleSelect?: (eventId: string) => void;
  onToggleSelectAll?: () => void;
}

export function EventTable({
  events,
  loading,
  onEventClick,
  eventTags = {},
  tagSuggestions = [],
  onAddTag = () => {},
  onRemoveTag = () => {},
  hasActiveFilters = false,
  onClearFilters,
  showTags = false,
  selectedIds = new Set(),
  onToggleSelect = () => {},
  onToggleSelectAll = () => {},
}: EventTableProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [tagInputs, setTagInputs] = useState<Record<string, string>>({});

  const allSelected =
    events.length > 0 && events.every((event) => selectedIds.has(event.id));
  const someSelected = events.some((event) => selectedIds.has(event.id));

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const getEventTypeColor = (eventType: string): string => {
    const hash = eventType
      .split("")
      .reduce((acc, char) => acc + char.charCodeAt(0), 0);

    const colors = [
      "rgba(0, 255, 156, 0.8)",
      "rgba(0, 212, 255, 0.8)",
      "rgba(255, 170, 0, 0.8)",
      "rgba(255, 102, 255, 0.8)",
    ];

    return colors[hash % colors.length];
  };

  const handleCardKeyDown = (
    event: KeyboardEvent<HTMLElement>,
    record: EventRecord,
  ) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onEventClick(record);
    }
  };

  const renderTags = (event: EventRecord) => (
    <div style={{ display: "grid", gap: "0.4rem" }}>
      <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
        {(eventTags[event.id] ?? []).map((tag) => (
          <span
            key={tag}
            className={styles.pill}
            style={{ fontSize: "0.72rem", padding: "0.2rem 0.45rem" }}
          >
            {tag}
            <button
              type="button"
              onClick={(clickEvent) => {
                clickEvent.stopPropagation();
                onRemoveTag(event.id, tag);
              }}
              style={{
                background: "transparent",
                border: 0,
                color: "inherit",
                cursor: "pointer",
                marginLeft: "0.3rem",
                padding: 0,
              }}
              title={`Remove ${tag}`}
              aria-label={`Remove tag ${tag} from event ${event.id}`}
            >
              x
            </button>
          </span>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.35rem" }}>
        <input
          className={styles.fieldInput}
          list={`event-tag-suggestions-${event.id}`}
          value={tagInputs[event.id] ?? ""}
          placeholder="add tag"
          aria-label={`Add tag to event ${event.id}`}
          onClick={(clickEvent) => clickEvent.stopPropagation()}
          onChange={(changeEvent) => {
            const value = changeEvent.target.value;
            setTagInputs((prev) => ({ ...prev, [event.id]: value }));
          }}
          onKeyDown={(keyEvent) => {
            if (keyEvent.key === "Enter") {
              keyEvent.preventDefault();
              keyEvent.stopPropagation();

              const value = tagInputs[event.id] ?? "";
              onAddTag(event.id, value);
              setTagInputs((prev) => ({ ...prev, [event.id]: "" }));
            }
          }}
          style={{ padding: "0.35rem 0.45rem", fontSize: "0.75rem" }}
        />

        <button
          type="button"
          className={styles.btn}
          style={{
            padding: "0.2rem 0.5rem",
            fontSize: "0.75rem",
            minWidth: "auto",
          }}
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();

            const value = tagInputs[event.id] ?? "";
            onAddTag(event.id, value);
            setTagInputs((prev) => ({ ...prev, [event.id]: "" }));
          }}
          title="Add tag"
          aria-label={`Add tag to event ${event.id}`}
        >
          +
        </button>
      </div>

      <datalist id={`event-tag-suggestions-${event.id}`}>
        {tagSuggestions.map((tag) => (
          <option key={tag} value={tag} />
        ))}
      </datalist>
    </div>
  );

  if (loading) {
    return <EventTableSkeleton showTags={showTags} />;
  }

  if (!events.length) {
    return (
      <div className={styles.tableWrap}>
        <div className={styles.emptyTable}>
          {hasActiveFilters ? (
            <EmptyState
              variant="terminal"
              icon={
                <EmptyStateIcon>
                  <Search className="h-8 w-8 text-terminal-gray" />
                </EmptyStateIcon>
              }
              title="No events match your criteria"
              description="We couldn't find any events matching your current search and filter settings. Try adjusting them or clear all filters to see more results."
              action={
                onClearFilters
                  ? {
                      label: "Clear Filters",
                      onClick: onClearFilters,
                      terminalVariant: "secondary",
                    }
                  : undefined
              }
            />
          ) : (
            <EmptyState
              variant="terminal"
              icon={
                <EmptyStateIcon>
                  <Inbox className="h-8 w-8 text-terminal-gray" />
                </EmptyStateIcon>
              }
              title="No events found"
              description="Select a contract and adjust filters to view events."
              action={{
                label: "View Contracts",
                href: "/contracts",
                ariaLabel: "Go to the contracts list",
                terminalVariant: "secondary",
              }}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <style>
        {`
          .soroscan-events-card-grid {
            display: none;
          }

          .soroscan-event-card {
            width: 100%;
            text-align: left;
            background: rgba(13, 21, 34, 0.92);
            border: 1px solid rgba(0, 212, 255, 0.25);
            border-radius: 10px;
            padding: 1rem;
            color: #d6f7ff;
            cursor: pointer;
            transition:
              border-color 0.2s ease,
              box-shadow 0.2s ease,
              transform 0.2s ease;
          }

          .soroscan-event-card:hover,
          .soroscan-event-card:focus {
            outline: none;
            border-color: rgba(0, 212, 255, 0.75);
            box-shadow: 0 0 18px rgba(0, 212, 255, 0.18);
            transform: translateY(-1px);
          }

          .soroscan-event-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 0.85rem;
          }

          .soroscan-event-card-title {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
          }

          .soroscan-event-card-label {
            font-size: 0.7rem;
            color: #7ba8b5;
            text-transform: uppercase;
            letter-spacing: 0.05rem;
          }

          .soroscan-event-card-grid-inner {
            display: grid;
            gap: 0.75rem;
          }

          .soroscan-event-card-row {
            display: flex;
            justify-content: space-between;
            gap: 0.75rem;
            border-top: 1px solid rgba(123, 168, 181, 0.14);
            padding-top: 0.65rem;
          }

          .soroscan-event-card-value {
            color: #d6f7ff;
            text-align: right;
            word-break: break-word;
          }

          .soroscan-event-card-footer {
            margin-top: 1rem;
            color: #00ff9c;
            font-size: 0.78rem;
            text-align: right;
          }

          @media (max-width: 639px) {
            .soroscan-events-table {
              display: none;
            }

            .soroscan-events-card-grid {
              display: grid;
              grid-template-columns: 1fr;
              gap: 0.9rem;
            }
          }

          @media (min-width: 640px) and (max-width: 1023px) {
            .soroscan-events-table {
              display: none;
            }

            .soroscan-events-card-grid {
              display: grid;
              grid-template-columns: repeat(2, 1fr);
              gap: 0.9rem;
            }
          }

          @media (min-width: 1024px) {
            .soroscan-events-table {
              display: table;
            }

            .soroscan-events-card-grid {
              display: none;
            }
          }
        `}
      </style>

      <table className={`${styles.eventTable} soroscan-events-table`}>
        <thead>
          <tr>
            <th className={`${toolbarStyles.checkboxCell} text-xs font-semibold uppercase tracking-wider text-muted-foreground`}>
              <IndeterminateCheckbox
                checked={allSelected}
                indeterminate={someSelected && !allSelected}
                onChange={onToggleSelectAll}
                aria-label={
                  allSelected ? "Deselect all events" : "Select all events"
                }
                id="select-all-events"
              />
            </th>
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Contract</th>
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Type</th>
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Ledger</th>
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Time</th>
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Transaction</th>
            {showTags && <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Tags</th>}
            <th className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => {
            const isSelected = selectedIds.has(event.id);

            return (
              <tr
                key={event.id}
                className={isSelected ? toolbarStyles.selectedRow : undefined}
                style={{
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
                onClick={() => onEventClick(event)}
                onMouseEnter={(mouseEvent) => {
                  if (!isSelected) {
                    mouseEvent.currentTarget.style.boxShadow = `0 0 15px ${getEventTypeColor(
                      event.eventType,
                    )}`;
                  }
                }}
                onMouseLeave={(mouseEvent) => {
                  mouseEvent.currentTarget.style.boxShadow = "none";
                }}
              >
                <td
                  className={toolbarStyles.checkboxCell}
                  onClick={(clickEvent) => clickEvent.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(event.id)}
                    aria-label={`Select event ${event.id}`}
                    id={`select-event-${event.id}`}
                  />
                </td>

                <td data-label="Contract">
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <code>{shortHash(event.contractId)}</code>
                    <button
                      type="button"
                      className={styles.btn}
                      style={{
                        padding: "0.2rem 0.4rem",
                        fontSize: "0.7rem",
                        minWidth: "auto",
                      }}
                      onClick={(clickEvent) => {
                        clickEvent.stopPropagation();
                        void copyToClipboard(
                          event.contractId,
                          `contract-${event.id}`,
                        );
                      }}
                      title="Copy contract ID"
                      aria-label={`Copy contract ID ${event.contractId}`}
                    >
                      {copiedId === `contract-${event.id}` ? "✓" : "📋"}
                    </button>
                  </div>
                </td>

                <td data-label="Type">
                  <span
                    className={styles.pill}
                    style={{
                      borderColor: getEventTypeColor(event.eventType),
                      backgroundColor: `${getEventTypeColor(event.eventType)}15`,
                      color: getEventTypeColor(event.eventType),
                    }}
                  >
                    {event.eventType}
                  </span>
                </td>

                <td data-label="Ledger">
                  <button
                    type="button"
                    className={styles.btn}
                    style={{
                      padding: "0.2rem 0.5rem",
                      fontSize: "0.75rem",
                    }}
                    onClick={(clickEvent) => {
                      clickEvent.stopPropagation();
                    }}
                    aria-label={`View ledger ${event.ledger} for event ${event.id}`}
                  >
                    {event.ledger}
                  </button>
                </td>

                <td data-label="Time">{formatDateTime(event.timestamp)}</td>

                <td data-label="Tx">
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <code>{shortHash(event.txHash)}</code>
                    <button
                      type="button"
                      className={styles.btn}
                      style={{
                        padding: "0.2rem 0.4rem",
                        fontSize: "0.7rem",
                        minWidth: "auto",
                      }}
                      onClick={(clickEvent) => {
                        clickEvent.stopPropagation();
                        void copyToClipboard(event.txHash, `tx-${event.id}`);
                      }}
                      title="Copy transaction hash"
                      aria-label={`Copy transaction hash ${event.txHash}`}
                    >
                      {copiedId === `tx-${event.id}` ? "✓" : "📋"}
                    </button>
                  </div>
                </td>

                {showTags && <td data-label="Tags">{renderTags(event)}</td>}

                <td data-label="Actions">
                  <button
                    type="button"
                    className={styles.btn}
                    style={{
                      padding: "0.3rem 0.6rem",
                      fontSize: "0.75rem",
                    }}
                    onClick={(clickEvent) => {
                      clickEvent.stopPropagation();
                      onEventClick(event);
                    }}
                    aria-label={`View details for event ${event.id}`}
                  >
                    View
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="soroscan-events-card-grid" data-testid="events-card-grid">
        {events.map((event) => {
          const isSelected = selectedIds.has(event.id);

          return (
            <article
              key={event.id}
              className="soroscan-event-card"
              data-testid="event-card"
              role="button"
              tabIndex={0}
              onClick={() => onEventClick(event)}
              onKeyDown={(keyEvent) => handleCardKeyDown(keyEvent, event)}
            >
              <div className="soroscan-event-card-header">
                <div className="soroscan-event-card-title">
                  <span className="soroscan-event-card-label">Event Type</span>
                  <span
                    className={styles.pill}
                    style={{
                      borderColor: getEventTypeColor(event.eventType),
                      backgroundColor: `${getEventTypeColor(event.eventType)}15`,
                      color: getEventTypeColor(event.eventType),
                    }}
                  >
                    {event.eventType}
                  </span>
                </div>

                <label
                  className={toolbarStyles.checkboxCell}
                  onClick={(clickEvent) => clickEvent.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(event.id)}
                    aria-label={`Select event ${event.id}`}
                  />
                </label>
              </div>

              <div className="soroscan-event-card-grid-inner">
                <div className="soroscan-event-card-row">
                  <span className="soroscan-event-card-label">Contract</span>
                  <span className="soroscan-event-card-value">
                    <code>{shortHash(event.contractId)}</code>
                  </span>
                </div>

                <div className="soroscan-event-card-row">
                  <span className="soroscan-event-card-label">Ledger</span>
                  <span className="soroscan-event-card-value">
                    {event.ledger}
                  </span>
                </div>

                <div className="soroscan-event-card-row">
                  <span className="soroscan-event-card-label">Time</span>
                  <span className="soroscan-event-card-value">
                    {formatDateTime(event.timestamp)}
                  </span>
                </div>

                <div className="soroscan-event-card-row">
                  <span className="soroscan-event-card-label">Transaction</span>
                  <span className="soroscan-event-card-value">
                    <code>{shortHash(event.txHash)}</code>
                  </span>
                </div>

                {showTags && (
                  <div className="soroscan-event-card-row">
                    <span className="soroscan-event-card-label">Tags</span>
                    <span className="soroscan-event-card-value">
                      {(eventTags[event.id] ?? []).join(", ") || "None"}
                    </span>
                  </div>
                )}
              </div>

              <div className="soroscan-event-card-footer">View details</div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

interface IndeterminateCheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  indeterminate?: boolean;
}

function IndeterminateCheckbox({
  indeterminate = false,
  ...props
}: IndeterminateCheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);

  return <input type="checkbox" ref={ref} {...props} />;
}