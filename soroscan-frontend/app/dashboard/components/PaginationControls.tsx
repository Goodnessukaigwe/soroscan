"use client";

import * as React from "react";
import styles from "@/components/ingest/ingest-terminal.module.css";
import { Dropdown } from "@/components/ui/dropdown";

interface PaginationControlsProps {
  currentPage: number;
  hasNext: boolean;
  hasPrev: boolean;
  onPageChange: (page: number) => void;
  startIndex: number;
  endIndex: number;
  totalCount: number;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
}

const PAGE_SIZE_OPTIONS = [
  { label: "10 per page", value: "10" },
  { label: "25 per page", value: "25" },
  { label: "50 per page", value: "50" },
  { label: "100 per page", value: "100" },
];

export function PaginationControls({
  currentPage,
  hasNext,
  hasPrev,
  onPageChange,
  startIndex,
  endIndex,
  totalCount,
  pageSize,
  onPageSizeChange,
}: PaginationControlsProps) {
  return (
    <div className={styles.paginationRow}>
      <button
        type="button"
        className={`${styles.btn} ${styles.secondaryBtn}`}
        disabled={currentPage === 1}
        onClick={() => onPageChange(1)}
        title="First page"
        aria-label="Go to first page"
      >
        ◄◄
      </button>
      
      <button
        type="button"
        className={`${styles.btn} ${styles.secondaryBtn}`}
        disabled={!hasPrev}
        onClick={() => onPageChange(currentPage - 1)}
        title="Previous page"
        aria-label="Go to previous page"
      >
        ◄ Previous
      </button>
      
      <span className={styles.pill}>
        Page {currentPage}
      </span>
      
      <span style={{ color: "#7ba8b5", fontSize: "0.85rem" }}>
        Showing {startIndex}-{endIndex} of {totalCount}+
      </span>

      <div style={{ width: "140px", marginLeft: "8px" }}>
        <Dropdown
          options={PAGE_SIZE_OPTIONS}
          value={pageSize.toString()}
          onChange={(value) => onPageSizeChange(parseInt(value))}
        />
      </div>
      
      <button
        type="button"
        className={`${styles.btn} ${styles.secondaryBtn}`}
        disabled={!hasNext}
        onClick={() => onPageChange(currentPage + 1)}
        title="Next page"
        aria-label="Go to next page"
      >
        Next ►
      </button>
      
      <button
        type="button"
        className={`${styles.btn} ${styles.secondaryBtn}`}
        disabled={!hasNext}
        onClick={() => {
          // Jump ahead by 10 pages
          onPageChange(currentPage + 10);
        }}
        title="Jump forward"
        aria-label="Jump forward 10 pages"
      >
        ►►
      </button>
    </div>
  );
}
