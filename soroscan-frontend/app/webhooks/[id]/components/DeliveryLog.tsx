"use client"

import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption,
  SortDirectionIndicator,
  type SortDirection,
} from "@/components/terminal/Table"
import type { DeliveryLog, SortField, StatusFilter } from "../../types"

type SortDir = SortDirection

interface DeliveryLogProps {
  logs: DeliveryLog[]
}

function StatusCodeBadge({ code }: { code: number }) {
  const cls =
    code < 300 ? "text-terminal-green border-terminal-green/40" :
    code < 500 ? "text-terminal-warning border-terminal-warning/40" :
                 "text-terminal-danger border-terminal-danger/40"
  return (
    <span className={`inline-flex items-center border px-1.5 py-0.5 text-[10px] font-terminal-mono ${cls}`}>
      {code}
    </span>
  )
}

function ExpandableError({ message }: { message: string }) {
  const [expanded, setExpanded] = React.useState(false)
  const short = message.length > 40 && !expanded ? message.slice(0, 40) + "…" : message
  return (
    <span className="text-terminal-danger text-[10px]">
      {short}
      {message.length > 40 && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="ml-1 text-terminal-cyan hover:text-terminal-green transition-colors underline underline-offset-2"
        >
          {expanded ? "[less]" : "[more]"}
        </button>
      )}
    </span>
  )
}

const PAGE_SIZE = 10

export function DeliveryLog({ logs }: DeliveryLogProps) {
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("ALL")
  const [sortField, setSortField] = React.useState<SortField>("timestamp")
  const [sortDir, setSortDir] = React.useState<SortDir>("desc")
  const [page, setPage] = React.useState(1)

  const toggleSort = (f: SortField) => {
    if (f === sortField) setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    else { setSortField(f); setSortDir("desc") }
    setPage(1)
  }

  const filtered = logs.filter((l) => {
    if (statusFilter === "ALL") return true
    if (statusFilter === "2xx") return l.statusCode >= 200 && l.statusCode < 300
    if (statusFilter === "4xx") return l.statusCode >= 400 && l.statusCode < 500
    if (statusFilter === "5xx") return l.statusCode >= 500
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0
    if (sortField === "timestamp")     cmp = a.timestamp.localeCompare(b.timestamp)
    if (sortField === "statusCode")    cmp = a.statusCode - b.statusCode
    if (sortField === "responseTimeMs") cmp = a.responseTimeMs - b.responseTimeMs
    if (sortField === "attempt")       cmp = a.attempt - b.attempt
    return sortDir === "asc" ? cmp : -cmp
    void cmp
  })

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const paginated = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <section className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-bold text-terminal-green whitespace-nowrap">
            [DELIVERY_LOGS]
          </h2>
          <div className="h-[2px] w-24 bg-terminal-green/20" />
          <span className="text-[10px] text-terminal-gray">{filtered.length} entries</span>
        </div>

        {/* Filter pill buttons */}
        <div className="flex gap-1.5 text-[10px]">
          {(["ALL", "2xx", "4xx", "5xx"] as StatusFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => { setStatusFilter(f); setPage(1) }}
              className={`px-2.5 py-1 border transition-colors font-terminal-mono ${
                statusFilter === f
                  ? f === "ALL" ? "border-terminal-green text-terminal-green bg-terminal-green/10"
                    : f === "2xx" ? "border-terminal-green text-terminal-green bg-terminal-green/10"
                    : f === "4xx" ? "border-terminal-warning text-terminal-warning bg-terminal-warning/10"
                    : "border-terminal-danger text-terminal-danger bg-terminal-danger/10"
                  : "border-terminal-gray/30 text-terminal-gray hover:border-terminal-green/50"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {paginated.length === 0 ? (
        <div className="border border-terminal-green/20 p-8 text-center text-terminal-gray text-sm">
          NO_LOGS_FOUND — try adjusting the filter
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                    onClick={() => toggleSort("timestamp")}
                  >
                    <span className="inline-flex items-center gap-1">
                      TIMESTAMP
                      <SortDirectionIndicator
                        active={sortField === "timestamp"}
                        direction={sortDir}
                      />
                    </span>
                  </TableHead>
                  <TableHead className="hidden sm:table-cell">EVENT_TYPE</TableHead>
                  <TableHead
                    className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                    onClick={() => toggleSort("statusCode")}
                  >
                    <span className="inline-flex items-center gap-1">
                      STATUS
                      <SortDirectionIndicator
                        active={sortField === "statusCode"}
                        direction={sortDir}
                      />
                    </span>
                  </TableHead>
                  <TableHead
                    className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                    onClick={() => toggleSort("responseTimeMs")}
                  >
                    <span className="inline-flex items-center gap-1">
                      RESP_TIME
                      <SortDirectionIndicator
                        active={sortField === "responseTimeMs"}
                        direction={sortDir}
                      />
                    </span>
                  </TableHead>
                  <TableHead
                    className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                    onClick={() => toggleSort("attempt")}
                  >
                    <span className="inline-flex items-center gap-1">
                      ATTEMPT
                      <SortDirectionIndicator
                        active={sortField === "attempt"}
                        direction={sortDir}
                      />
                    </span>
                  </TableHead>
                  <TableHead>ERROR_MSG</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginated.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-[10px] whitespace-nowrap text-terminal-gray">
                      {new Date(log.timestamp).toLocaleString("en-GB", {
                        dateStyle: "short",
                        timeStyle: "medium",
                      })}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-[10px] text-terminal-cyan">
                      {log.eventType}
                    </TableCell>
                    <TableCell>
                      <StatusCodeBadge code={log.statusCode} />
                    </TableCell>
                    <TableCell className="text-[10px]">
                      <span className={log.responseTimeMs > 600 ? "text-terminal-warning" : "text-terminal-gray"}>
                        {log.responseTimeMs}ms
                      </span>
                    </TableCell>
                    <TableCell className="text-[10px] text-terminal-gray">
                      #{log.attempt}
                    </TableCell>
                    <TableCell>
                      {log.errorMessage
                        ? <ExpandableError message={log.errorMessage} />
                        : <span className="text-terminal-green text-[10px]">OK</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
              {paginated.length > 0 && (
                <TableCaption>
                  Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, sorted.length)} of {sorted.length} delivery attempts
                </TableCaption>
              )}
            </Table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-[10px] text-terminal-gray">
              <span>Page {page} of {totalPages}</span>
              <div className="flex gap-1">
                <button
                  disabled={page === 1}
                  onClick={() => setPage(1)}
                  className="px-2 py-1 border border-terminal-gray/30 hover:border-terminal-green hover:text-terminal-green transition-colors disabled:opacity-30"
                >
                  «
                </button>
                <button
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="px-2 py-1 border border-terminal-gray/30 hover:border-terminal-green hover:text-terminal-green transition-colors disabled:opacity-30"
                >
                  <ChevronLeft size={10} />
                </button>
                <button
                  disabled={page === totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-2 py-1 border border-terminal-gray/30 hover:border-terminal-green hover:text-terminal-green transition-colors disabled:opacity-30"
                >
                  <ChevronRight size={10} />
                </button>
                <button
                  disabled={page === totalPages}
                  onClick={() => setPage(totalPages)}
                  className="px-2 py-1 border border-terminal-gray/30 hover:border-terminal-green hover:text-terminal-green transition-colors disabled:opacity-30"
                >
                  »
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
