"use client";

import { useState, useEffect, type Dispatch, type SetStateAction } from "react";
import { Filter } from "lucide-react";
import { fetchEventTypes } from "@/components/ingest/graphql";
import { Drawer } from "@/components/ui/drawer";
import styles from "@/components/ingest/ingest-terminal.module.css";

interface FilterBarProps {
  contracts: Array<{ contractId: string; name: string }>;
  filters: {
    contractId: string;
    eventType: string;
    since: string;
    until: string;
    searchQuery: string;
    tags: string[];
  };
  onFilterChange: (filters: Partial<FilterBarProps["filters"]>) => void;
  onExport: () => void;
  tagSuggestions: string[];
  /** `sidebar` = vertical filter column for dashboard IA (#910) */
  variant?: "inline" | "sidebar";
}

function normalizeTag(tag: string): string {
  return tag.trim().toLowerCase().replace(/\s+/g, "-");
}

function FilterForm({
  contracts,
  localFilters,
  setLocalFilters,
  eventTypes,
  tagInput,
  setTagInput,
  onAddTagFilter,
  onRemoveTagFilter,
  onApply,
  onClear,
  onExport,
  tagSuggestions,
}: {
  contracts: FilterBarProps["contracts"];
  localFilters: FilterBarProps["filters"];
  setLocalFilters: Dispatch<SetStateAction<FilterBarProps["filters"]>>;
  eventTypes: string[];
  tagInput: string;
  setTagInput: Dispatch<SetStateAction<string>>;
  onAddTagFilter: () => void;
  onRemoveTagFilter: (tag: string) => void;
  onApply: () => void;
  onClear: () => void;
  onExport: (format: "csv" | "json") => void;
  tagSuggestions: string[];
}) {
  return (
    <>
      <div className={styles.controlGrid}>
        <label className={styles.fieldRow} htmlFor="contract-select">
          <span>Contract</span>
          <select
            id="contract-select"
            className={styles.fieldInput}
            value={localFilters.contractId}
            onChange={(e) =>
              setLocalFilters((prev) => ({
                ...prev,
                contractId: e.target.value,
                eventType: "",
              }))
            }
          >
            <option value="">All Contracts</option>
            {contracts.map((contract) => (
              <option key={contract.contractId} value={contract.contractId}>
                {contract.name || contract.contractId}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.fieldRow} htmlFor="event-type-select">
          <span>Event Type</span>
          <select
            id="event-type-select"
            className={styles.fieldInput}
            value={localFilters.eventType}
            onChange={(e) =>
              setLocalFilters((prev) => ({ ...prev, eventType: e.target.value }))
            }
            disabled={!localFilters.contractId}
          >
            <option value="">All Types</option>
            {eventTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.fieldRow} htmlFor="date-since">
          <span>From</span>
          <input
            id="date-since"
            className={styles.fieldInput}
            type="datetime-local"
            value={localFilters.since}
            onChange={(e) =>
              setLocalFilters((prev) => ({ ...prev, since: e.target.value }))
            }
          />
        </label>

        <label className={styles.fieldRow} htmlFor="date-until">
          <span>To</span>
          <input
            id="date-until"
            className={styles.fieldInput}
            type="datetime-local"
            value={localFilters.until}
            onChange={(e) =>
              setLocalFilters((prev) => ({ ...prev, until: e.target.value }))
            }
          />
        </label>

        <label className={styles.fieldRow} htmlFor="tag-filter-input">
          <span>Tag Filter</span>
          <div style={{ display: "flex", gap: "0.45rem" }}>
            <input
              id="tag-filter-input"
              className={styles.fieldInput}
              list="event-tag-suggestions"
              placeholder="add tag filter"
              aria-label="Add tag filter"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onAddTagFilter();
                }
              }}
            />
            <button
              type="button"
              className={styles.btn}
              style={{ padding: "0.45rem 0.75rem", minWidth: "auto" }}
              onClick={onAddTagFilter}
              title="Add tag filter"
              aria-label="Add tag filter"
            >
              +
            </button>
          </div>
          <datalist id="event-tag-suggestions">
            {tagSuggestions.map((tag) => (
              <option key={tag} value={tag} />
            ))}
          </datalist>
          {!!localFilters.tags.length && (
            <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
              {localFilters.tags.map((tag) => (
                <span key={tag} className={styles.pill}>
                  {tag}
                  <button
                    type="button"
                    onClick={() => onRemoveTagFilter(tag)}
                    style={{
                      background: "transparent",
                      border: 0,
                      color: "inherit",
                      marginLeft: "0.35rem",
                      cursor: "pointer",
                      padding: 0,
                    }}
                    title={`Remove ${tag}`}
                    aria-label={`Remove tag filter ${tag}`}
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
          )}
        </label>
      </div>

      <div className={styles.row}>
        <button type="button" className={styles.btn} onClick={onApply}>
          Apply Filters
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.secondaryBtn}`}
          onClick={onClear}
        >
          Clear
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.secondaryBtn}`}
          onClick={() => onExport("csv")}
        >
          Export CSV
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.secondaryBtn}`}
          onClick={() => onExport("json")}
        >
          Export JSON
        </button>
      </div>
    </>
  );
}

export function FilterBar({
  contracts,
  filters,
  onFilterChange,
  onExport,
  tagSuggestions,
  variant = "inline",
}: FilterBarProps) {
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [localFilters, setLocalFilters] = useState(filters);
  const [tagInput, setTagInput] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  useEffect(() => {
    if (!filters.contractId) {
      setEventTypes([]);
      return;
    }

    const loadEventTypes = async () => {
      try {
        const types = await fetchEventTypes(filters.contractId);
        setEventTypes(types);
      } catch (err) {
        console.error("Failed to load event types:", err);
        setEventTypes([]);
      }
    };

    loadEventTypes();
  }, [filters.contractId]);

  const handleApply = () => {
    onFilterChange(localFilters);
    setDrawerOpen(false);
  };

  const handleClear = () => {
    const cleared = {
      contractId: "",
      eventType: "",
      since: "",
      until: "",
      searchQuery: "",
      tags: [],
    };
    setLocalFilters(cleared);
    setTagInput("");
    onFilterChange(cleared);
    setDrawerOpen(false);
  };

  const handleAddTagFilter = () => {
    const normalized = normalizeTag(tagInput);
    if (!normalized) {
      return;
    }

    setLocalFilters((prev) => {
      if (prev.tags.includes(normalized)) {
        return prev;
      }
      return { ...prev, tags: [...prev.tags, normalized] };
    });
    setTagInput("");
  };

  const handleRemoveTagFilter = (tagToRemove: string) => {
    setLocalFilters((prev) => ({
      ...prev,
      tags: prev.tags.filter((tag) => tag !== tagToRemove),
    }));
  };

  const activeFilterCount = [
    localFilters.contractId,
    localFilters.eventType,
    localFilters.since,
    localFilters.until,
    ...localFilters.tags,
  ].filter(Boolean).length;

  const formProps = {
    contracts,
    localFilters,
    setLocalFilters,
    eventTypes,
    tagInput,
    setTagInput,
    onAddTagFilter: handleAddTagFilter,
    onRemoveTagFilter: handleRemoveTagFilter,
    onApply: handleApply,
    onClear: handleClear,
    onExport,
    tagSuggestions,
  };

  return (
    <>
      {/* Mobile: filter toggle button */}
      <div className="sm:hidden mb-3">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className={`${styles.btn} w-full flex items-center justify-center gap-2`}
          data-testid="filter-panel-toggle"
          aria-expanded={drawerOpen}
          aria-controls="mobile-filter-panel"
          aria-label={drawerOpen ? "Close event filters" : "Open event filters"}
        >
          <Filter size={16} aria-hidden="true" />
          Filters
          {activeFilterCount > 0 && (
            <span className={styles.pill} style={{ fontSize: "0.72rem" }}>
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Mobile: slide-in filter drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        position="right"
        title="Event Filters"
        className="sm:hidden"
        id="mobile-filter-panel"
      >
        <FilterForm {...formProps} />
      </Drawer>

      {/* Desktop: sidebar or inline filter panel */}
      <section
        className={`${styles.controls} hidden sm:block ${
          variant === "sidebar" ? styles.filterSidebar : ""
        }`}
        aria-label="Event filters"
        data-variant={variant}
      >
        <div
          className={`${styles.controlCard} ${
            variant === "sidebar" ? styles.filterSidebarCard : ""
          }`}
        >
          <h2 className={styles.sectionTitle}>Filters</h2>
          <FilterForm {...formProps} />
        </div>
      </section>
    </>
  );
}
