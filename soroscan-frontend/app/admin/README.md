# Admin Dashboard

The admin section lives at `app/admin/` inside the Next.js frontend. It provides a terminal-styled operations dashboard for platform operators: real-time system metrics, webhook health, CDC sync status, audit logs, and data-quality tooling.

Access is guarded by `AuthGuard` (admin role required). The layout wraps every page in `AppShell` for consistent navigation.

---

## Local Development

```bash
# from soroscan-frontend/
pnpm install
pnpm dev
```

Open `http://localhost:3000/admin`.

The GraphQL proxy at `/api/graphql` forwards requests to the Django backend. Set `BACKEND_BASE_URL` in `.env.local` when running outside Docker:

```env
BACKEND_BASE_URL=http://localhost:8000
```

---

## Directory Layout

```
app/admin/
├── layout.tsx              # AuthGuard + AppShell wrapper for all admin routes
├── page.tsx                # Main system dashboard (metrics, chart, error log)
│
├── components/             # Admin-only UI components (not shared with the rest of the app)
│   ├── ErrorLog.tsx        # Live scrollable system error feed
│   ├── EventChart.tsx      # Ingestion timeline bar/line chart
│   ├── MetricsCard.tsx     # Single-stat card with icon and colour variant
│   └── WebhookStats.tsx    # Webhook success rate and avg delivery time summary
│
├── audit-logs/
│   └── page.tsx            # Audit trail viewer
│
├── cdc/
│   └── page.tsx            # CDC (Change-Data-Capture) sync monitoring
│
├── contracts-import/
│   └── page.tsx            # Bulk contract import tooling
│
├── data-quality/
│   └── page.tsx            # Data quality scorecards and reconciliation
│
├── dedup/
│   └── page.tsx            # Event deduplication log viewer
│
└── queries/
    └── GetSystemMetrics.graphql   # GraphQL query for the main dashboard
```

---

## Component Patterns

### MetricsCard

A single-stat display card. Accepts a `color` variant (`green`, `cyan`, `warning`, `danger`, `gray`) that controls the border, background tint, and icon colour — all mapped to the terminal design-token palette.

```tsx
<MetricsCard
  title="Webhook Health"
  value="98%"
  subValue="Last 24h Success Rate"
  icon={Webhook}
  color="green"
  loading={false}
/>
```

Props:

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `string` | — | Card label shown in brackets above the value |
| `value` | `string \| number` | — | Primary stat value |
| `subValue` | `string` | — | Optional secondary label below the value |
| `icon` | `LucideIcon` | — | Lucide icon rendered top-right |
| `color` | `"green" \| "cyan" \| "warning" \| "danger" \| "gray"` | `"green"` | Colour variant |
| `loading` | `boolean` | `false` | Shows `---` placeholder and pulses the icon while true |

### ErrorLog

A scrollable live error feed. Renders items with `ERROR` (red left border) or `WARNING` (yellow left border) severity badges, timestamps, and an optional `context` field.

```tsx
<ErrorLog errors={data.recentErrors} loading={loading} />
```

### EventChart

Renders the 24-hour ingestion timeline. Receives a `data` array of `{ label, value }` objects and a `title` string.

### WebhookStats

Displays webhook success rate and average delivery time. Accepts `successRate` (0–100), `avgTime` (ms), and `loading`.

### Page layout helpers

Admin pages use two shared layout components from `components/layout/`:

- `AdminDashboardLayout` — wraps the dashboard in a responsive grid with named `header`, `metrics`, `charts`, and `logs` slots.
- `DashboardPanel` — a styled panel container used inside grid cells. Accepts an `elevation` prop (`"default"` | `"elevated"`) and an optional `title`.

---

## Data Fetching

The main dashboard polls `fetchSystemMetrics()` (from `components/ingest/graphql.ts`) every 30 seconds. The GraphQL query is defined in `queries/GetSystemMetrics.graphql`.

After modifying any GraphQL query or the backend schema, regenerate the typed hooks:

```bash
pnpm run codegen
```

---

## Design Conventions

- **Terminal aesthetic**: all text is uppercase, monospaced (`font-terminal-mono`), and uses the `terminal-*` Tailwind colour tokens (`terminal-green`, `terminal-cyan`, `terminal-danger`, etc.).
- **No inline styles**: use Tailwind classes and the existing colour token map in each component.
- **Component scope**: components in `app/admin/components/` are local to the admin section. Shared UI primitives (buttons, badges, spinners) come from `components/terminal/` or `components/ui/`.
- **Auth**: every admin route inherits `AuthGuard` from `layout.tsx` — individual pages do not need to repeat the guard.
