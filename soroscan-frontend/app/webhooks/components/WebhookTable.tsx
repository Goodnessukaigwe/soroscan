"use client"

import * as React from "react"
import Link from "next/link"
import { Trash2, FlaskConical } from "lucide-react"
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  SortDirectionIndicator,
  type SortDirection,
} from "@/components/terminal/Table"
import { Button } from "@/components/terminal/Button"
import type { Webhook, WebhookStatus } from "../types"

interface WebhookTableProps {
  webhooks: Webhook[]
  onDelete: (id: string) => void
  onTest: (id: string) => void
  testingId?: string | null
  testResult?: { id: string; ok: boolean; code: number } | null
}

type SortField = "url" | "status" | "successRate" | "lastDelivery"
type SortDir = SortDirection

function StatusBadge({ status }: { status: WebhookStatus }) {
  const map: Record<WebhookStatus, { dot: string; label: string; text: string }> = {
    ACTIVE:    { dot: "bg-terminal-green animate-pulse shadow-glow-green", label: "ACTIVE",     text: "text-terminal-green" },
    SUSPENDED: { dot: "bg-terminal-warning",                               label: "SUSPENDED",  text: "text-terminal-warning" },
    FAILED:    { dot: "bg-terminal-danger animate-pulse",                  label: "FAILED",     text: "text-terminal-danger" },
  }
  const { dot, label, text } = map[status]
  return (
    <span className={`inline-flex items-center gap-1.5 text-[10px] font-terminal-mono ${text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  )
}

function SuccessBar({ rate }: { rate: number }) {
  const colour = rate >= 90 ? "bg-terminal-green" : rate >= 60 ? "bg-terminal-warning" : "bg-terminal-danger"
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-terminal-gray/20 rounded-none">
        <div className={`h-full ${colour}`} style={{ width: `${rate}%` }} />
      </div>
      <span className="text-[10px]">{rate.toFixed(1)}%</span>
    </div>
  )
}

export function WebhookTable({ webhooks, onDelete, onTest, testingId, testResult }: WebhookTableProps) {
  const [sortField, setSortField] = React.useState<SortField>("lastDelivery")
  const [sortDir, setSortDir] = React.useState<SortDir>("desc")

  const toggleSort = (f: SortField) => {
    if (f === sortField) setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    else { setSortField(f); setSortDir("desc") }
  }

  const sorted = [...webhooks].sort((a, b) => {
    let cmp = 0
    if (sortField === "url") cmp = a.url.localeCompare(b.url)
    else if (sortField === "status") cmp = a.status.localeCompare(b.status)
    else if (sortField === "successRate") cmp = a.successRate - b.successRate
    else if (sortField === "lastDelivery") {
      cmp = (a.lastDelivery ?? "").localeCompare(b.lastDelivery ?? "")
    }
    return sortDir === "asc" ? cmp : -cmp
  })

  if (webhooks.length === 0) {
    return (
      <div className="border border-terminal-green/20 p-12 text-center font-terminal-mono space-y-3">
        <div className="text-terminal-green text-2xl">[ ]</div>
        <div className="text-terminal-gray text-sm">NO_SUBSCRIPTIONS_FOUND</div>
        <div className="text-terminal-gray/50 text-xs">Create your first webhook to start receiving events</div>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead
              className="cursor-pointer select-none hover:text-terminal-green transition-colors"
              onClick={() => toggleSort("status")}
            >
              <span className="inline-flex items-center gap-1">
                STATUS
                <SortDirectionIndicator active={sortField === "status"} direction={sortDir} />
              </span>
            </TableHead>
            <TableHead
              className="cursor-pointer select-none hover:text-terminal-green transition-colors"
              onClick={() => toggleSort("url")}
            >
              <span className="inline-flex items-center gap-1">
                ENDPOINT_URL
                <SortDirectionIndicator active={sortField === "url"} direction={sortDir} />
              </span>
            </TableHead>
            <TableHead className="hidden md:table-cell">EVENT_TYPES</TableHead>
            <TableHead
              className="cursor-pointer select-none hover:text-terminal-green transition-colors"
              onClick={() => toggleSort("successRate")}
            >
              <span className="inline-flex items-center gap-1">
                SUCCESS
                <SortDirectionIndicator active={sortField === "successRate"} direction={sortDir} />
              </span>
            </TableHead>
            <TableHead
              className="cursor-pointer select-none hover:text-terminal-green transition-colors"
              onClick={() => toggleSort("lastDelivery")}
            >
              <span className="inline-flex items-center gap-1">
                LAST_DELIVERY
                <SortDirectionIndicator active={sortField === "lastDelivery"} direction={sortDir} />
              </span>
            </TableHead>
            <TableHead>ACTIONS</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((wh) => {
            const isTesting = testingId === wh.id
            const result = testResult?.id === wh.id ? testResult : null
            return (
              <TableRow key={wh.id}>
                {/* Status */}
                <TableCell><StatusBadge status={wh.status} /></TableCell>

                {/* URL */}
                <TableCell>
                  <div className="max-w-[180px] sm:max-w-[280px] lg:max-w-none">
                    <Link
                      href={`/webhooks/${wh.id}`}
                      className="text-terminal-cyan hover:text-terminal-green transition-colors text-[11px] block truncate font-terminal-mono"
                    >
                      {wh.url}
                    </Link>
                    {wh.contractFilter && (
                      <div className="text-[9px] text-terminal-gray/60 mt-0.5">
                        CONTRACT: {wh.contractFilter}
                      </div>
                    )}
                    {result && (
                      <div className={`text-[9px] mt-1 ${result.ok ? "text-terminal-green" : "text-terminal-danger"}`}>
                        {result.ok ? `✓ TEST_OK (${result.code})` : `✗ TEST_FAILED (${result.code})`}
                      </div>
                    )}
                  </div>
                </TableCell>

                {/* Event types */}
                <TableCell className="hidden md:table-cell">
                  <div className="flex flex-wrap gap-1 max-w-[200px]">
                    {wh.eventTypes.slice(0, 3).map((t) => (
                      <span key={t} className="text-[9px] border border-terminal-green/30 px-1 text-terminal-gray">
                        {t === "ALL" ? "ALL_EVENTS" : t}
                      </span>
                    ))}
                    {wh.eventTypes.length > 3 && (
                      <span className="text-[9px] text-terminal-gray/60">+{wh.eventTypes.length - 3}</span>
                    )}
                  </div>
                </TableCell>

                {/* Success rate */}
                <TableCell><SuccessBar rate={wh.successRate} /></TableCell>

                {/* Last delivery */}
                <TableCell className="text-[11px] whitespace-nowrap text-terminal-gray">
                  {wh.lastDelivery
                    ? new Date(wh.lastDelivery).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })
                    : "—"}
                  {wh.lastStatusCode && (
                    <div className={`text-[9px] mt-0.5 ${wh.lastStatusCode < 300 ? "text-terminal-green" : "text-terminal-danger"}`}>
                      HTTP {wh.lastStatusCode}
                    </div>
                  )}
                </TableCell>

                {/* Actions */}
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <Link href={`/webhooks/${wh.id}`}>
                      <Button variant="secondary" size="sm" className="text-[9px] h-7 px-2 hidden sm:inline-flex">
                        DETAIL
                      </Button>
                    </Link>
                    <button
                      onClick={() => onTest(wh.id)}
                      disabled={isTesting}
                      title="Test webhook"
                      className="h-7 w-7 flex items-center justify-center border border-terminal-cyan/40 text-terminal-cyan hover:border-terminal-cyan hover:bg-terminal-cyan/10 transition-colors disabled:opacity-50"
                    >
                      <FlaskConical size={12} />
                    </button>
                    <button
                      onClick={() => onDelete(wh.id)}
                      title="Delete webhook"
                      className="h-7 w-7 flex items-center justify-center border border-terminal-danger/40 text-terminal-danger hover:border-terminal-danger hover:bg-terminal-danger/10 transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
