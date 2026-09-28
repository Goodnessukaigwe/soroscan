/**
 * EventTableSkeleton – shimmer placeholder for event table rows.
 *
 * Design spec (issue #989):
 * ──────────────────────────────────────────────────────────────────
 * Layout types:
 *   • Desktop (≥ 1024px)  – <table> with 8 columns
 *   • Tablet  (640-1023px) – 2-column card grid
 *   • Mobile  (< 640px)    – single-column card grid
 *
 * Each skeleton row mirrors the dimensions of the real row:
 *   Checkbox  16×16   (rounded-md)
 *   Contract  120×20  (rounded)
 *   Type       80×24  (rounded-full, pill shape)
 *   Ledger     60×24  (rounded)
 *   Time      140×20  (rounded)
 *   Tx        100×20  (rounded)
 *   Tags      120×24  (rounded)
 *   Actions    50×28  (rounded)
 *
 * Shimmer animation:
 *   • Gradient: muted → muted-foreground/10 → muted (blue-cyan terminal palette)
 *   • Duration: 1.5s ease-in-out infinite
 *   • Direction: horizontal sweep (left → right)
 *   • bg-size: 200% 100%
 *
 * Responsive rules:
 *   • Table is hidden on tablet/mobile; card grid is hidden on desktop.
 *   • Skeleton cards use the same card chrome (border, background, padding)
 *     as real event cards so layout shift is zero.
 * ──────────────────────────────────────────────────────────────────
 */

import { Skeleton } from "@/components/ui/skeleton";
import styles from "@/components/ingest/ingest-terminal.module.css";
import toolbarStyles from "@/app/dashboard/components/BulkActionsToolbar.module.css";

const ROW_COUNT = 5;

export function EventTableSkeleton({ showTags = false }: { showTags?: boolean }) {
  return (
    <div className={styles.tableWrap}>
      {/* Inline responsive CSS – same breakpoints as EventTable */}
      <style>{`
        .soroscan-events-card-grid-sk { display: none; }
        @media (max-width: 639px) {
          .soroscan-events-table-sk { display: none; }
          .soroscan-events-card-grid-sk { display: grid; grid-template-columns: 1fr; gap: 0.9rem; }
        }
        @media (min-width: 640px) and (max-width: 1023px) {
          .soroscan-events-table-sk { display: none; }
          .soroscan-events-card-grid-sk { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.9rem; }
        }
        @media (min-width: 1024px) {
          .soroscan-events-table-sk { display: table; }
          .soroscan-events-card-grid-sk { display: none; }
        }
      `}</style>

      {/* ── Desktop table skeleton ── */}
      <table className={`${styles.eventTable} soroscan-events-table-sk`}>
        <thead>
          <tr>
            <th className={`${toolbarStyles.checkboxCell} text-xs font-semibold uppercase tracking-wider text-muted-foreground`} aria-hidden="true">
              <Skeleton variant="rectangle" width={16} height={16} />
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
          {Array.from({ length: ROW_COUNT }).map((_, i) => (
            <tr key={`sk-row-${i}`}>
              <td className={toolbarStyles.checkboxCell}>
                <Skeleton variant="rectangle" width={16} height={16} />
              </td>
              <td data-label="Contract">
                <Skeleton variant="rectangle" width={120} height={20} />
              </td>
              <td data-label="Type">
                <Skeleton variant="rectangle" width={80} height={24} className="rounded-full" />
              </td>
              <td data-label="Ledger">
                <Skeleton variant="rectangle" width={60} height={24} />
              </td>
              <td data-label="Time">
                <Skeleton variant="rectangle" width={140} height={20} />
              </td>
              <td data-label="Tx">
                <Skeleton variant="rectangle" width={100} height={20} />
              </td>
              {showTags && (
                <td data-label="Tags">
                  <Skeleton variant="rectangle" width={120} height={24} />
                </td>
              )}
              <td data-label="Actions">
                <Skeleton variant="rectangle" width={50} height={28} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ── Mobile/tablet card grid skeleton ── */}
      <div className="soroscan-events-card-grid-sk" aria-hidden="true">
        {Array.from({ length: ROW_COUNT }).map((_, i) => (
          <div
            key={`sk-card-${i}`}
            className="soroscan-event-card"
            style={{ pointerEvents: "none" }}
          >
            <div className="soroscan-event-card-header">
              <div className="soroscan-event-card-title">
                <span className="soroscan-event-card-label">Event Type</span>
                <Skeleton variant="rectangle" width={80} height={24} className="rounded-full" />
              </div>
              <Skeleton variant="rectangle" width={20} height={20} />
            </div>

            <div className="soroscan-event-card-grid-inner">
              <div className="soroscan-event-card-row">
                <span className="soroscan-event-card-label">Contract</span>
                <Skeleton variant="rectangle" width={80} height={16} />
              </div>
              <div className="soroscan-event-card-row">
                <span className="soroscan-event-card-label">Ledger</span>
                <Skeleton variant="rectangle" width={50} height={16} />
              </div>
              <div className="soroscan-event-card-row">
                <span className="soroscan-event-card-label">Time</span>
                <Skeleton variant="rectangle" width={120} height={16} />
              </div>
              <div className="soroscan-event-card-row">
                <span className="soroscan-event-card-label">Transaction</span>
                <Skeleton variant="rectangle" width={90} height={16} />
              </div>
            </div>

            <div className="soroscan-event-card-footer">
              <Skeleton variant="rectangle" width={80} height={14} />
            </div>
          </div>
        ))}
      </div>

      {/* Accessible loading announcement */}
      <div role="status" aria-live="polite" className="sr-only">
        Loading events…
      </div>
    </div>
  );
}
