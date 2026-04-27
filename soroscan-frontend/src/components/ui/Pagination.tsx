"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

type PaginationToken = number | "ellipsis"

export interface PaginationProps {
  totalItems: number
  pageSize: number
  currentPage: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  pageSizeOptions?: number[]
  maxVisiblePages?: number
  className?: string
}

function clampPage(page: number, totalPages: number): number {
  if (totalPages <= 0) {
    return 1
  }

  if (page < 1) {
    return 1
  }

  if (page > totalPages) {
    return totalPages
  }

  return page
}

function getPaginationRange(currentPage: number, totalPages: number, maxVisiblePages: number): PaginationToken[] {
  if (totalPages <= maxVisiblePages) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }

  const safeMaxVisible = Math.max(5, maxVisiblePages)
  const siblingCount = Math.max(1, Math.floor((safeMaxVisible - 3) / 2))
  const leftSiblingIndex = Math.max(currentPage - siblingCount, 1)
  const rightSiblingIndex = Math.min(currentPage + siblingCount, totalPages)

  const showLeftEllipsis = leftSiblingIndex > 2
  const showRightEllipsis = rightSiblingIndex < totalPages - 1

  if (!showLeftEllipsis && showRightEllipsis) {
    const leftItemCount = safeMaxVisible - 2
    const leftRange = Array.from({ length: leftItemCount }, (_, i) => i + 1)
    return [...leftRange, "ellipsis", totalPages]
  }

  if (showLeftEllipsis && !showRightEllipsis) {
    const rightItemCount = safeMaxVisible - 2
    const start = totalPages - rightItemCount + 1
    const rightRange = Array.from({ length: rightItemCount }, (_, i) => start + i)
    return [1, "ellipsis", ...rightRange]
  }

  const middleRange = Array.from(
    { length: rightSiblingIndex - leftSiblingIndex + 1 },
    (_, i) => leftSiblingIndex + i
  )

  return [1, "ellipsis", ...middleRange, "ellipsis", totalPages]
}

export function Pagination({
  totalItems,
  pageSize,
  currentPage,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50],
  maxVisiblePages = 5,
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  const safeCurrentPage = clampPage(currentPage, totalPages)

  const pageRange = React.useMemo(
    () => getPaginationRange(safeCurrentPage, totalPages, maxVisiblePages),
    [safeCurrentPage, totalPages, maxVisiblePages]
  )

  const isFirstPage = safeCurrentPage === 1
  const isLastPage = safeCurrentPage === totalPages

  return (
    <nav className={cn("flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between", className)} aria-label="Pagination Navigation">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Page {safeCurrentPage} of {totalPages}
      </p>

      <div className="flex items-center gap-2">
        <label htmlFor="pagination-page-size" className="text-sm text-muted-foreground">
          Rows per page
        </label>
        <select
          id="pagination-page-size"
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          aria-label="Page size"
        >
          {pageSizeOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          aria-label="First page"
          onClick={() => onPageChange(1)}
          disabled={isFirstPage}
          className="h-9 rounded-md border border-input px-3 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          First
        </button>
        <button
          type="button"
          aria-label="Previous page"
          onClick={() => onPageChange(safeCurrentPage - 1)}
          disabled={isFirstPage}
          className="h-9 rounded-md border border-input px-3 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          Prev
        </button>

        {pageRange.map((token, index) => {
          if (token === "ellipsis") {
            return (
              <span
                key={`ellipsis-${index}`}
                aria-hidden="true"
                className="inline-flex h-9 items-center px-2 text-sm text-muted-foreground"
              >
                ...
              </span>
            )
          }

          const isActive = token === safeCurrentPage

          return (
            <button
              key={token}
              type="button"
              onClick={() => onPageChange(token)}
              aria-label={`Go to page ${token}`}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "h-9 min-w-9 rounded-md border px-3 text-sm",
                isActive
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input"
              )}
            >
              <span className="sr-only">Page </span>
              {token}
            </button>
          )
        })}

        <button
          type="button"
          aria-label="Next page"
          onClick={() => onPageChange(safeCurrentPage + 1)}
          disabled={isLastPage}
          className="h-9 rounded-md border border-input px-3 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
        <button
          type="button"
          aria-label="Last page"
          onClick={() => onPageChange(totalPages)}
          disabled={isLastPage}
          className="h-9 rounded-md border border-input px-3 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          Last
        </button>
      </div>
    </nav>
  )
}

export { getPaginationRange }
