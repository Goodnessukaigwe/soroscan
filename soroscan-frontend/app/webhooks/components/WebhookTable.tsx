"use client"

import * as React from "react"
import Link from "next/link"
import { Trash2, FlaskConical, ChevronDown, ChevronUp, Plus } from "lucide-react"
import { EmptyState, EmptyStateIcon } from "@/components/ui/empty-state"
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  SortDirectionIndicator,
  type SortDirection,
} from "@/components/terminal/Table"
import { Button } from "@/components/terminal/Button"
import { WebhookDeliveryStatusBadge, getDeliveryState } from "@/components/ui/WebhookDeliveryStatusBadge"
import type { Webhook, WebhookStatus } from "../types"

interface WebhookTableProps {
  webhooks: Webhook[]
  onDelete: (id: string) => void
  onTest: (id: string) => void
  onCreate?: () => void
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

// ── Mobile card for a single webhook ──────────────────────────────────────

function WebhookCard({
  wh,
  onDelete,
  onTest,
  isTesting,
  result,
}: {
  wh: Webhook
  onDelete: (id: string) => void
  onTest: (id: string) => void
  isTesting: boolean
  result: { ok: boolean; code: number } | null
}) {
  const [expanded, setExpanded] = React.useState(false)

  return (
    <div className="border border-terminal-green/20 font-terminal-mono" data-testid="webhook-card">
      {/* Primary row — always visible */}
      <div className="flex items-center gap-3 p-3">
        <StatusBadge status={wh.status} />

        <Link
          href={`/webhooks/${wh.id}`}
          className="flex-1 text-terminal-cyan hover:text-terminal-green transition-colors text-[11px] truncate"
        >
          {wh.url}
        </Link>

        {/* Touch-friendly expand toggle */}
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse details" : "Expand details"}
          className="min-w-[44px] min-h-[44px] flex items-center justify-center text-terminal-gray hover:text-terminal-green transition-colors"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Collapsible details */}
      {expanded && (
        <div className="border-t border-terminal-green/10 px-3 pb-3 space-y-2 text-[10px]">
          {/* Event types */}
          <div className="flex flex-wrap gap-1 pt-2">
            {wh.eventTypes.slice(0, 5).map((t) => (
              <span key={t} className="border border-terminal-green/30 px-1 text-terminal-gray">
                {t === "ALL" ? "ALL_EVENTS" : t}
              </span>
            ))}
            {wh.eventTypes.length > 5 && (
              <span className="text-terminal-gray/60">+{wh.eventTypes.length - 5}</span>
            )}
          </div>

          {/* Success rate */}
          <div className="flex items-center gap-2">
            <span className="text-terminal-gray w-20">SUCCESS</span>
            <SuccessBar rate={wh.successRate} />
          </div>

          {/* Last delivery */}
          <div className="flex items-center gap-2">
            <span className="text-terminal-gray w-20">LAST_DELIVERY</span>
            <span className="text-terminal-gray">
              {wh.lastDelivery
                ? new Date(wh.lastDelivery).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })
                : "—"}
            </span>
            {wh.lastStatusCode && (
              <span className={`text-[9px] ${wh.lastStatusCode < 300 ? "text-terminal-green" : "text-terminal-danger"}`}>
                HTTP {wh.lastStatusCode}
              </span>
            )}
          </div>

          {/* Delivery status */}
          <div className="flex items-center gap-2">
            <span className="text-terminal-gray w-20">STATUS</span>
            <WebhookDeliveryStatusBadge
              state={getDeliveryState(
                wh.isActive ?? true,
                wh.lastDeliverySuccess ??
                  (wh.lastStatusCode !== undefined ? wh.lastStatusCode < 300 : true),
                wh.failureCount ?? 0
              )}
              lastDeliveryTime={wh.lastDelivery}
              isActive={wh.isActive ?? true}
              failureCount={wh.failureCount ?? 0}
            />
          </div>

          {/* Contract filter */}
          {wh.contractFilter && (
            <div className="flex items-center gap-2">
              <span className="text-terminal-gray w-20">CONTRACT</span>
              <span className="text-terminal-gray/80">{wh.contractFilter}</span>
            </div>
          )}

          {/* Test result */}
          {result && (
            <div className={`text-[9px] ${result.ok ? "text-terminal-green" : "text-terminal-danger"}`}>
              {result.ok ? `✓ TEST_OK (${result.code})` : `✗ TEST_FAILED (${result.code})`}
            </div>
          )}

          {/* Actions — touch-friendly (min 44px) */}
          <div className="flex gap-2 pt-1">
            <Link href={`/webhooks/${wh.id}`} className="flex-1">
              <Button variant="secondary" size="sm" className="w-full text-[9px] min-h-[44px]">
                DETAIL
              </Button>
            </Link>
            <button
              type="button"
              onClick={() => onTest(wh.id)}
              disabled={isTesting}
              title="Test webhook"
              aria-label={`Test webhook ${wh.id}`}
              data-testid={`test-webhook-${wh.id}`}
              className="min-w-[44px] min-h-[44px] flex items-center justify-center border border-terminal-cyan/40 text-terminal-cyan hover:border-terminal-cyan hover:bg-terminal-cyan/10 transition-colors disabled:opacity-50"
            >
              <FlaskConical size={14} />
            </button>
            <button
              type="button"
              onClick={() => onDelete(wh.id)}
              title="Delete webhook"
              aria-label={`Delete webhook ${wh.id}`}
              data-testid={`delete-webhook-${wh.id}`}
              className="min-w-[44px] min-h-[44px] flex items-center justify-center border border-terminal-danger/40 text-terminal-danger hover:border-terminal-danger hover:bg-terminal-danger/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function WebhookTable({ webhooks, onDelete, onTest, onCreate, testingId, testResult }: WebhookTableProps) {
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
      <EmptyState
        variant="terminal"
        ariaLabel="No webhook subscriptions configured"
        icon={
          <EmptyStateIcon>
            <div className="text-terminal-green text-2xl">[ ]</div>
          </EmptyStateIcon>
        }
        title="No webhooks configured"
        description="Subscribe an endpoint to start receiving real-time contract event deliveries."
        action={
          onCreate
            ? {
                id: "empty-state-create-webhook",
                label: "New Webhook",
                onClick: onCreate,
                ariaLabel: "Create your first webhook",
                terminalVariant: "primary",
                size: "lg",
                icon: <Plus className="h-4 w-4" aria-hidden="true" />,
              }
            : undefined
        }
      />
    )
  }

  return (
    <>
      {/* Mobile: stacked cards (hidden on sm+) */}
      <div className="sm:hidden space-y-2" data-testid="webhook-mobile-list">
        {sorted.map((wh) => (
          <WebhookCard
            key={wh.id}
            wh={wh}
            onDelete={onDelete}
            onTest={onTest}
            isTesting={testingId === wh.id}
            result={testResult?.id === wh.id ? testResult : null}
          />
        ))}
      </div>

      {/* Desktop: table (hidden below sm) */}
      <div className="hidden sm:block overflow-x-auto" data-testid="webhook-desktop-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead
                className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                onClick={() => toggleSort("status")}
              >
                <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  STATUS
                  <SortDirectionIndicator active={sortField === "status"} direction={sortDir} />
                </span>
              </TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                onClick={() => toggleSort("url")}
              >
                <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  ENDPOINT_URL
                  <SortDirectionIndicator active={sortField === "url"} direction={sortDir} />
                </span>
              </TableHead>
              <TableHead>EVENT_TYPES</TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                onClick={() => toggleSort("successRate")}
              >
                <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  SUCCESS
                  <SortDirectionIndicator active={sortField === "successRate"} direction={sortDir} />
                </span>
              </TableHead>
              <TableHead
                className="cursor-pointer select-none hover:text-terminal-green transition-colors"
                onClick={() => toggleSort("lastDelivery")}
              >
                <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  LAST_DELIVERY
                  <SortDirectionIndicator active={sortField === "lastDelivery"} direction={sortDir} />
                </span>
              </TableHead>
              <TableHead>DELIVERY_STATUS</TableHead>
              <TableHead>ACTIONS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((wh) => {
              const isTesting = testingId === wh.id
              const result = testResult?.id === wh.id ? testResult : null
              return (
                <TableRow key={wh.id}>
                  <TableCell><StatusBadge status={wh.status} /></TableCell>
                  <TableCell>
                    <div className="max-w-[280px] lg:max-w-none">
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
                  <TableCell>
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
                  <TableCell><SuccessBar rate={wh.successRate} /></TableCell>
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
                  <TableCell>
                    <WebhookDeliveryStatusBadge
                      state={getDeliveryState(
                        wh.isActive ?? true,
                        wh.lastDeliverySuccess ?? (wh.lastStatusCode ? wh.lastStatusCode < 300 : true),
                        wh.failureCount ?? 0
                      )}
                      lastDeliveryTime={wh.lastDelivery}
                      isActive={wh.isActive ?? true}
                      failureCount={wh.failureCount ?? 0}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <Link href={`/webhooks/${wh.id}`}>
                        <Button variant="secondary" size="sm" className="text-[9px] h-7 px-2">
                          DETAIL
                        </Button>
                      </Link>
                      <button
                        type="button"
                        onClick={() => onTest(wh.id)}
                        disabled={isTesting}
                        title="Test webhook"
                        aria-label={`Test webhook ${wh.id}`}
                        data-testid="test-webhook-btn"
                        className="h-7 w-7 flex items-center justify-center border border-terminal-cyan/40 text-terminal-cyan hover:border-terminal-cyan hover:bg-terminal-cyan/10 transition-colors disabled:opacity-50"
                      >
                        <FlaskConical size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(wh.id)}
                        title="Delete webhook"
                        aria-label={`Delete webhook ${wh.id}`}
                        data-testid="delete-webhook-btn"
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
    </>
  )
}