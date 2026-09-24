/**
 * Tests for CDC Monitoring Dashboard (#917).
 */
import React from 'react';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// ── Mock recharts so tests run without canvas ─────────────────────────────────
jest.mock('recharts', () => {
  const React = jest.requireActual('react');
  const Mock = ({ children, 'data-testid': tid }: { children?: React.ReactNode; 'data-testid'?: string }) =>
    <div data-testid={tid}>{children}</div>;
  return {
    LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    ReferenceLine: () => null,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  };
});

global.URL.createObjectURL = jest.fn(() => 'blob:mock');
global.URL.revokeObjectURL = jest.fn();

import { getFreshnessLevel, FRESHNESS_COLORS } from '@/components/cdc-monitoring/freshnessUtils';
import { CDCSyncDashboard } from '@/components/cdc-monitoring/CDCSyncDashboard';
import { SyncStatusCard } from '@/components/cdc-monitoring/SyncStatusCard';
import { TableLevelMetrics } from '@/components/cdc-monitoring/TableLevelMetrics';
import { DataFreshnessHeatmap } from '@/components/cdc-monitoring/DataFreshnessHeatmap';
import { SyncLogViewer } from '@/components/cdc-monitoring/SyncLogViewer';
import { CDCLatencyChart } from '@/components/cdc-monitoring/CDCLatencyChart';
import { SyncConfigForm } from '@/components/cdc-monitoring/SyncConfigForm';
import type {
  CDCSyncProgress,
  TableSyncMetric,
  SyncLogEntry,
  LatencyDataPoint,
  FreshnessCell,
} from '@/components/cdc-monitoring/types';
import type { CDCSyncSummary } from '@/components/cdc-monitoring/CDCSyncDashboard';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const NOW = new Date().toISOString();
const ONE_HOUR_AGO = new Date(Date.now() - 61 * 60 * 1000).toISOString();
const TWO_DAYS_AGO = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();

const PROGRESS_RUNNING: CDCSyncProgress = {
  syncId: 'sync-1',
  status: 'running',
  rowsSynced: 50000,
  rowsUpdated: 1200,
  rowsDeleted: 30,
  latencyMs: 320,
  lastSyncAt: NOW,
  nextSyncAt: new Date(Date.now() + 30000).toISOString(),
  errorMessage: null,
};

const PROGRESS_FAILED: CDCSyncProgress = {
  syncId: 'sync-2',
  status: 'failed',
  rowsSynced: 0,
  rowsUpdated: 0,
  rowsDeleted: 0,
  latencyMs: 0,
  lastSyncAt: ONE_HOUR_AGO,
  nextSyncAt: null,
  errorMessage: 'Connection timeout after 30s',
};

const SYNCS: CDCSyncSummary[] = [
  { syncId: 'sync-1', name: 'Snowflake Prod', progress: PROGRESS_RUNNING },
  { syncId: 'sync-2', name: 'BigQuery Analytics', progress: PROGRESS_FAILED },
];

const TABLE_METRICS: TableSyncMetric[] = [
  { tableName: 'events', rowsSynced: 100000, rowsUpdated: 500, rowsDeleted: 10, lastSyncAt: NOW, latencyMs: 200, status: 'running' },
  { tableName: 'contracts', rowsSynced: 5000, rowsUpdated: 50, rowsDeleted: 0, lastSyncAt: ONE_HOUR_AGO, latencyMs: 6000, status: 'idle' },
];

const LOGS: SyncLogEntry[] = [
  { id: 'l1', syncId: 'sync-1', timestamp: NOW, level: 'info', message: 'Sync started', tableName: 'events', status: 'running' },
  { id: 'l2', syncId: 'sync-1', timestamp: NOW, level: 'error', message: 'Row insert failed', tableName: 'contracts', status: 'failed' },
  { id: 'l3', syncId: 'sync-1', timestamp: NOW, level: 'warn', message: 'Latency spike detected', tableName: null, status: null },
];

const LATENCY_DATA: LatencyDataPoint[] = Array.from({ length: 10 }, (_, i) => ({
  timestamp: new Date(Date.now() - (9 - i) * 30000).toISOString(),
  latencyMs: 200 + i * 50,
}));

const FRESHNESS_CELLS: FreshnessCell[] = [
  { tableName: 'events', lastSyncAt: NOW, level: 'fresh' },
  { tableName: 'contracts', lastSyncAt: ONE_HOUR_AGO, level: 'stale' },
  { tableName: 'webhooks', lastSyncAt: TWO_DAYS_AGO, level: 'error' },
];

// ── freshnessUtils ────────────────────────────────────────────────────────────

describe('getFreshnessLevel', () => {
  it('returns "fresh" for timestamp < 1 hour ago', () => {
    expect(getFreshnessLevel(new Date(Date.now() - 10 * 60 * 1000).toISOString())).toBe('fresh');
  });

  it('returns "stale" for timestamp between 1 hour and 1 day ago', () => {
    expect(getFreshnessLevel(ONE_HOUR_AGO)).toBe('stale');
  });

  it('returns "error" for timestamp > 1 day ago', () => {
    expect(getFreshnessLevel(TWO_DAYS_AGO)).toBe('error');
  });

  it('returns "error" for null', () => {
    expect(getFreshnessLevel(null)).toBe('error');
  });

  it('FRESHNESS_COLORS has entries for all three levels', () => {
    expect(FRESHNESS_COLORS.fresh).toBeDefined();
    expect(FRESHNESS_COLORS.stale).toBeDefined();
    expect(FRESHNESS_COLORS.error).toBeDefined();
  });
});

// ── CDCSyncDashboard ──────────────────────────────────────────────────────────

describe('CDCSyncDashboard', () => {
  it('renders with correct total sync count', () => {
    render(<CDCSyncDashboard syncs={SYNCS} />);
    expect(screen.getByTestId('total-syncs-count')).toHaveTextContent('2');
  });

  it('shows running count', () => {
    render(<CDCSyncDashboard syncs={SYNCS} />);
    expect(screen.getByTestId('running-syncs-count')).toHaveTextContent('1');
  });

  it('shows failed count with alert role when failures exist', () => {
    render(<CDCSyncDashboard syncs={SYNCS} />);
    expect(screen.getByTestId('failed-syncs-count')).toHaveTextContent('1');
    expect(screen.getByTestId('failed-syncs-count')).toHaveAttribute('role', 'alert');
  });

  it('does not show failed count when no failures', () => {
    const okSyncs: CDCSyncSummary[] = [
      { syncId: 's1', name: 'OK', progress: { ...PROGRESS_RUNNING, syncId: 's1' } },
    ];
    render(<CDCSyncDashboard syncs={okSyncs} />);
    expect(screen.queryByTestId('failed-syncs-count')).not.toBeInTheDocument();
  });

  it('renders a SyncStatusCard for each sync', () => {
    render(<CDCSyncDashboard syncs={SYNCS} />);
    expect(screen.getByTestId('sync-status-card-sync-1')).toBeInTheDocument();
    expect(screen.getByTestId('sync-status-card-sync-2')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(<CDCSyncDashboard syncs={[]} isLoading />);
    expect(screen.getByTestId('dashboard-loading')).toBeInTheDocument();
  });

  it('shows empty state when no syncs', () => {
    render(<CDCSyncDashboard syncs={[]} />);
    expect(screen.getByTestId('dashboard-empty')).toBeInTheDocument();
  });
});

// ── SyncStatusCard ────────────────────────────────────────────────────────────

describe('SyncStatusCard', () => {
  it('renders sync name', () => {
    render(<SyncStatusCard syncId="s1" name="Snowflake Prod" progress={PROGRESS_RUNNING} />);
    expect(screen.getByTestId('sync-name-s1')).toHaveTextContent('Snowflake Prod');
  });

  it('shows status badge with correct role', () => {
    render(<SyncStatusCard syncId="s1" name="Test" progress={PROGRESS_RUNNING} />);
    expect(screen.getByTestId('sync-status-s1')).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('sync-status-s1')).toHaveTextContent('running');
  });

  it('shows rows synced metric', () => {
    render(<SyncStatusCard syncId="s1" name="Test" progress={PROGRESS_RUNNING} />);
    expect(screen.getByTestId('sync-status-card-s1')).toHaveTextContent('50,000');
  });

  it('shows latency in ms', () => {
    render(<SyncStatusCard syncId="s1" name="Test" progress={PROGRESS_RUNNING} />);
    expect(screen.getByTestId('sync-latency-s1')).toHaveTextContent('320 ms');
  });

  it('highlights high latency in red', () => {
    const highLatency = { ...PROGRESS_RUNNING, latencyMs: 6000 };
    render(<SyncStatusCard syncId="s1" name="Test" progress={highLatency} />);
    expect(screen.getByTestId('sync-latency-s1')).toHaveClass('text-red-400');
  });

  it('shows error message when present', () => {
    render(<SyncStatusCard syncId="s2" name="Test" progress={PROGRESS_FAILED} />);
    expect(screen.getByTestId('sync-error-s2')).toHaveTextContent('Connection timeout after 30s');
  });

  it('shows retry button on failed status', () => {
    render(<SyncStatusCard syncId="s2" name="Test" progress={PROGRESS_FAILED} onRetry={jest.fn()} />);
    expect(screen.getByTestId('retry-btn-s2')).toBeInTheDocument();
  });

  it('calls onRetry with syncId when retry clicked', () => {
    const onRetry = jest.fn();
    render(<SyncStatusCard syncId="s2" name="Test" progress={PROGRESS_FAILED} onRetry={onRetry} />);
    fireEvent.click(screen.getByTestId('retry-btn-s2'));
    expect(onRetry).toHaveBeenCalledWith('s2');
  });

  it('shows trigger sync button', () => {
    render(<SyncStatusCard syncId="s1" name="Test" progress={PROGRESS_RUNNING} onTriggerSync={jest.fn()} />);
    expect(screen.getByTestId('trigger-btn-s1')).toBeInTheDocument();
  });

  it('calls onTriggerSync with syncId', () => {
    const onTrigger = jest.fn();
    render(<SyncStatusCard syncId="s1" name="Test" progress={PROGRESS_RUNNING} onTriggerSync={onTrigger} />);
    fireEvent.click(screen.getByTestId('trigger-btn-s1'));
    expect(onTrigger).toHaveBeenCalledWith('s1');
  });

  it('shows loading placeholder when isLoading', () => {
    render(<SyncStatusCard syncId="s1" name="Test" progress={null} isLoading />);
    expect(screen.getByTestId('sync-loading-s1')).toBeInTheDocument();
  });
});

// ── TableLevelMetrics ─────────────────────────────────────────────────────────

describe('TableLevelMetrics', () => {
  it('renders a row per table', () => {
    render(<TableLevelMetrics metrics={TABLE_METRICS} />);
    expect(screen.getByTestId('table-metric-row-events')).toBeInTheDocument();
    expect(screen.getByTestId('table-metric-row-contracts')).toBeInTheDocument();
  });

  it('shows rows synced, updated, deleted', () => {
    render(<TableLevelMetrics metrics={TABLE_METRICS} />);
    const row = screen.getByTestId('table-metric-row-events');
    expect(row).toHaveTextContent('100,000');
    expect(row).toHaveTextContent('500');
    expect(row).toHaveTextContent('10');
  });

  it('highlights high-latency row in red', () => {
    render(<TableLevelMetrics metrics={TABLE_METRICS} />);
    expect(screen.getByTestId('table-latency-contracts')).toHaveClass('text-red-400');
  });

  it('shows normal latency in green', () => {
    render(<TableLevelMetrics metrics={TABLE_METRICS} />);
    expect(screen.getByTestId('table-latency-events')).toHaveClass('text-green-400');
  });

  it('renders empty state when no metrics', () => {
    render(<TableLevelMetrics metrics={[]} />);
    expect(screen.getByTestId('table-metrics-empty')).toBeInTheDocument();
  });
});

// ── DataFreshnessHeatmap ──────────────────────────────────────────────────────

describe('DataFreshnessHeatmap', () => {
  it('renders a cell per table', () => {
    render(<DataFreshnessHeatmap cells={FRESHNESS_CELLS} />);
    expect(screen.getByTestId('heatmap-cell-events')).toBeInTheDocument();
    expect(screen.getByTestId('heatmap-cell-contracts')).toBeInTheDocument();
    expect(screen.getByTestId('heatmap-cell-webhooks')).toBeInTheDocument();
  });

  it('applies green class for fresh cell', () => {
    render(<DataFreshnessHeatmap cells={FRESHNESS_CELLS} />);
    expect(screen.getByTestId('heatmap-cell-events')).toHaveClass('text-green-400');
  });

  it('applies yellow class for stale cell', () => {
    render(<DataFreshnessHeatmap cells={FRESHNESS_CELLS} />);
    expect(screen.getByTestId('heatmap-cell-contracts')).toHaveClass('text-yellow-400');
  });

  it('applies red class for error cell', () => {
    render(<DataFreshnessHeatmap cells={FRESHNESS_CELLS} />);
    expect(screen.getByTestId('heatmap-cell-webhooks')).toHaveClass('text-red-400');
  });

  it('has accessible aria-label on each cell', () => {
    render(<DataFreshnessHeatmap cells={FRESHNESS_CELLS} />);
    expect(screen.getByTestId('heatmap-cell-events')).toHaveAttribute('aria-label', expect.stringContaining('events'));
  });

  it('renders empty state when no cells', () => {
    render(<DataFreshnessHeatmap cells={[]} />);
    expect(screen.getByTestId('heatmap-empty')).toBeInTheDocument();
  });
});

// ── SyncLogViewer ─────────────────────────────────────────────────────────────

describe('SyncLogViewer', () => {
  it('renders all log entries', () => {
    render(<SyncLogViewer logs={LOGS} />);
    expect(screen.getByTestId('log-entry-l1')).toBeInTheDocument();
    expect(screen.getByTestId('log-entry-l2')).toBeInTheDocument();
    expect(screen.getByTestId('log-entry-l3')).toBeInTheDocument();
  });

  it('shows correct level for each entry', () => {
    render(<SyncLogViewer logs={LOGS} />);
    expect(screen.getByTestId('log-level-l1')).toHaveTextContent('info');
    expect(screen.getByTestId('log-level-l2')).toHaveTextContent('error');
    expect(screen.getByTestId('log-level-l3')).toHaveTextContent('warn');
  });

  it('filters by table name', () => {
    render(<SyncLogViewer logs={LOGS} />);
    fireEvent.change(screen.getByTestId('log-filter-table'), {
      target: { value: 'events' },
    });
    expect(screen.getByTestId('log-entry-l1')).toBeInTheDocument();
    expect(screen.queryByTestId('log-entry-l2')).not.toBeInTheDocument();
  });

  it('filters by status', () => {
    render(<SyncLogViewer logs={LOGS} />);
    fireEvent.change(screen.getByTestId('log-filter-status'), {
      target: { value: 'failed' },
    });
    expect(screen.getByTestId('log-entry-l2')).toBeInTheDocument();
    expect(screen.queryByTestId('log-entry-l1')).not.toBeInTheDocument();
  });

  it('shows empty message when filters match nothing', () => {
    render(<SyncLogViewer logs={LOGS} />);
    fireEvent.change(screen.getByTestId('log-filter-table'), {
      target: { value: 'nonexistent_table' },
    });
    expect(screen.getByTestId('log-empty')).toBeInTheDocument();
  });

  it('export button triggers download', () => {
    const anchorClick = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<SyncLogViewer logs={LOGS} />);
    fireEvent.click(screen.getByTestId('log-export-button'));
    expect(global.URL.createObjectURL).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    anchorClick.mockRestore();
  });

  it('export button is disabled when log list is empty', () => {
    render(<SyncLogViewer logs={[]} />);
    expect(screen.getByTestId('log-export-button')).toBeDisabled();
  });

  it('log container has role="log" for accessibility', () => {
    render(<SyncLogViewer logs={LOGS} />);
    expect(screen.getByTestId('sync-log-list')).toHaveAttribute('role', 'log');
  });
});

// ── CDCLatencyChart ───────────────────────────────────────────────────────────

describe('CDCLatencyChart', () => {
  it('renders chart container with data', () => {
    render(<CDCLatencyChart data={LATENCY_DATA} />);
    expect(screen.getByTestId('cdc-latency-chart')).toBeInTheDocument();
  });

  it('renders recharts LineChart', () => {
    render(<CDCLatencyChart data={LATENCY_DATA} />);
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
  });

  it('renders empty state when no data', () => {
    render(<CDCLatencyChart data={[]} />);
    expect(screen.getByTestId('latency-chart-empty')).toBeInTheDocument();
  });

  it('shows target latency label', () => {
    render(<CDCLatencyChart data={LATENCY_DATA} targetLatencyMs={5000} />);
    expect(screen.getByTestId('cdc-latency-chart')).toHaveTextContent('5,000');
  });

  it('has accessible aria-label', () => {
    render(<CDCLatencyChart data={LATENCY_DATA} />);
    expect(screen.getByTestId('cdc-latency-chart')).toHaveAttribute(
      'aria-label',
      'CDC sync latency over time'
    );
  });
});

// ── SyncConfigForm ────────────────────────────────────────────────────────────

describe('SyncConfigForm', () => {
  const fillForm = () => {
    fireEvent.change(screen.getByTestId('cfg-name'), { target: { value: 'My Sync' } });
    fireEvent.change(screen.getByTestId('cfg-host'), { target: { value: 'acct.snowflakecomputing.com' } });
    fireEvent.change(screen.getByTestId('cfg-database'), { target: { value: 'DW' } });
    fireEvent.change(screen.getByTestId('cfg-schema'), { target: { value: 'PUBLIC' } });
    fireEvent.change(screen.getByTestId('cfg-username'), { target: { value: 'user' } });
    fireEvent.change(screen.getByTestId('cfg-password'), { target: { value: 'secret' } });
  };

  it('renders the form', () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn()} />);
    expect(screen.getByTestId('sync-config-form')).toBeInTheDocument();
  });

  it('shows validation error when name is empty', async () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn()} />);
    await act(async () => { fireEvent.click(screen.getByTestId('cfg-submit-button')); });
    expect(screen.getByTestId('cfg-error')).toHaveTextContent('Name is required');
  });

  it('shows validation error when host is empty', async () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn()} />);
    fireEvent.change(screen.getByTestId('cfg-name'), { target: { value: 'My Sync' } });
    await act(async () => { fireEvent.submit(screen.getByTestId('sync-config-form')); });
    expect(screen.getByTestId('cfg-error')).toHaveTextContent(/Host is required/i);
  });

  it('calls onSubmit with config when form is valid', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<SyncConfigForm onSubmit={onSubmit} onTestConnection={jest.fn()} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('cfg-submit-button')); });
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My Sync', host: 'acct.snowflakecomputing.com' })
    );
  });

  it('does not include password in a logged/visible way — password field type is password', () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn()} />);
    expect(screen.getByTestId('cfg-password')).toHaveAttribute('type', 'password');
  });

  it('calls onTestConnection when test button clicked', async () => {
    const onTest = jest.fn().mockResolvedValue({ ok: true, message: 'Connected!' });
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={onTest} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('test-connection-button')); });
    expect(onTest).toHaveBeenCalled();
  });

  it('shows success test result', async () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn().mockResolvedValue({ ok: true, message: 'Connected!' })} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('test-connection-button')); });
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Connected!');
  });

  it('shows failure test result', async () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn().mockResolvedValue({ ok: false, message: 'Auth failed' })} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('test-connection-button')); });
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Auth failed');
  });

  it('shows saved confirmation after successful submit', async () => {
    render(<SyncConfigForm onSubmit={jest.fn().mockResolvedValue(undefined)} onTestConnection={jest.fn()} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('cfg-submit-button')); });
    expect(screen.getByTestId('cfg-saved')).toBeInTheDocument();
  });

  it('shows error message on submit failure', async () => {
    render(<SyncConfigForm onSubmit={jest.fn().mockRejectedValue(new Error('Network error'))} onTestConnection={jest.fn()} />);
    fillForm();
    await act(async () => { fireEvent.click(screen.getByTestId('cfg-submit-button')); });
    expect(screen.getByTestId('cfg-error')).toHaveTextContent('Network error');
  });

  it('warehouse type select has all four options', () => {
    render(<SyncConfigForm onSubmit={jest.fn()} onTestConnection={jest.fn()} />);
    const select = screen.getByTestId('cfg-warehouse-type') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain('snowflake');
    expect(options).toContain('bigquery');
    expect(options).toContain('redshift');
    expect(options).toContain('databricks');
  });
});
