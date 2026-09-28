import * as React from "react"
import { cn } from "@/lib/utils"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  SortDirection,
  SortDirectionIndicator,
} from "./Table"

export interface ColumnDefinition<T = unknown> {
  /** Unique identifier for the column */
  key: string
  /** Display label for the column header */
  label: string
  /** Icon component to display next to the label in card view */
  icon?: React.ComponentType<{ className?: string }>
  /** Function to render cell content */
  render?: (item: T, value: unknown) => React.ReactNode
  /** Whether this column is sortable */
  sortable?: boolean
  /** CSS classes for the column */
  className?: string
  /** CSS classes for the cell content */
  cellClassName?: string
}

export interface ResponsiveTableProps<T = unknown> {
  /** Array of data items to display */
  data: T[]
  /** Column definitions */
  columns: ColumnDefinition<T>[]
  /** Current sort configuration */
  sort?: {
    key: string
    direction: SortDirection
  }
  /** Sort change handler */
  onSortChange?: (key: string, direction: SortDirection) => void
  /** Additional CSS classes for the table container */
  className?: string
  /** Additional CSS classes for individual cards */
  cardClassName?: string
  /** Loading state */
  loading?: boolean
  /** Empty state message */
  emptyMessage?: string
  /** Accessible caption for the table */
  caption?: string
}

/**
 * ResponsiveTable - Renders as a table on desktop (≥768px) and cards on mobile
 * 
 * Features:
 * - Table layout on desktop with sortable columns
 * - Card layout on mobile with icon + label + value stacking
 * - Terminal styling consistent with existing components
 * - Accessible with proper ARIA labels and focus management
 */
export function ResponsiveTable<T = unknown>({
  data,
  columns,
  sort,
  onSortChange,
  className,
  cardClassName,
  loading = false,
  emptyMessage = "No data available",
  caption,
}: ResponsiveTableProps<T>) {
  const handleSort = (key: string) => {
    if (!onSortChange) return
    
    const newDirection: SortDirection = 
      sort?.key === key && sort.direction === "asc" ? "desc" : "asc"
    
    onSortChange(key, newDirection)
  }

  const getValue = (item: T, column: ColumnDefinition<T>) => {
    return (item as Record<string, unknown>)[column.key]
  }

  const renderCellContent = (item: T, column: ColumnDefinition<T>) => {
    const value = getValue(item, column)
    return column.render ? column.render(item, value) : (value as React.ReactNode)
  }

  if (loading) {
    return (
      <div className={cn("w-full", className)}>
        {/* Desktop loading skeleton */}
        <div className="hidden md:block">
          <div className="relative w-full overflow-auto border-terminal border-terminal-green">
            <div className="w-full bg-terminal-green/10 border-b-terminal border-terminal-green h-10" />
            {[...Array(3)].map((_, i) => (
              <div key={i} className="border-b border-terminal-green/30 h-12 bg-terminal-green/5" />
            ))}
          </div>
        </div>
        
        {/* Mobile loading skeleton */}
        <div className="md:hidden space-y-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="border-terminal border-terminal-green bg-terminal-black/80 p-4 space-y-2"
            >
              {columns.slice(0, 3).map((_, j) => (
                <div key={j} className="flex items-center gap-3">
                  <div className="w-4 h-4 bg-terminal-green/20 rounded" />
                  <div className="w-16 h-3 bg-terminal-green/20 rounded" />
                  <div className="flex-1 h-3 bg-terminal-green/20 rounded" />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className={cn("w-full", className)}>
        <div className="text-center py-8 text-terminal-gray font-terminal-mono">
          {emptyMessage}
        </div>
      </div>
    )
  }

  return (
    <div className={cn("w-full", className)}>
      {/* Desktop Table View (≥768px) */}
      <div className="hidden md:block">
        <Table>
          {caption && (
            <caption className="sr-only">{caption}</caption>
          )}
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead 
                  key={column.key}
                  className={cn(
                    column.className,
                    column.sortable && "cursor-pointer select-none hover:bg-terminal-green/20"
                  )}
                  onClick={column.sortable ? () => handleSort(column.key) : undefined}
                  role={column.sortable ? "button" : undefined}
                  tabIndex={column.sortable ? 0 : undefined}
                  onKeyDown={
                    column.sortable 
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            handleSort(column.key)
                          }
                        }
                      : undefined
                  }
                  aria-sort={
                    column.sortable && sort?.key === column.key
                      ? sort.direction === "asc" ? "ascending" : "descending"
                      : column.sortable ? "none" : undefined
                  }
                >
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {column.label}
                    {column.sortable && (
                      <SortDirectionIndicator
                        active={sort?.key === column.key}
                        direction={sort?.direction || "asc"}
                        className="text-terminal-green"
                      />
                    )}
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((item, index) => (
              <TableRow key={index}>
                {columns.map((column) => (
                  <TableCell 
                    key={column.key}
                    className={column.cellClassName}
                  >
                    {renderCellContent(item, column)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile Card View (<768px) */}
      <div className="md:hidden space-y-3">
        {data.map((item, index) => (
          <div
            key={index}
            className={cn(
              "border-terminal border-terminal-green bg-terminal-black/80 p-4 space-y-3 hover:bg-terminal-green/10 hover:shadow-glow-green/20 transition-colors",
              cardClassName
            )}
          >
            {columns.map((column) => {
              const value = renderCellContent(item, column)
              
              // Skip empty values in card view for cleaner display
              if (value == null || value === "") return null
              
              return (
                <div key={column.key} className="flex items-center gap-3">
                  {/* Icon */}
                  {column.icon && (
                    <column.icon className="w-4 h-4 text-terminal-cyan flex-shrink-0" />
                  )}
                  
                  {/* Label */}
                  <div className="text-xs text-terminal-cyan uppercase tracking-wider font-bold min-w-[80px] flex-shrink-0">
                    {column.label}:
                  </div>
                  
                  {/* Value */}
                  <div className={cn(
                    "text-terminal-green font-terminal-mono flex-1 text-sm",
                    column.cellClassName
                  )}>
                    {value}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

export default ResponsiveTable