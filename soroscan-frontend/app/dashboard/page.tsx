"use client";

import { useMemo, useState } from "react";

type HealthState = "healthy" | "degraded" | "critical";

interface MetricSnapshot {
  apiP95Ms: number;
  apiP99Ms: number;
  cacheHitRate: number;
  errorRate: number;
  queueDepth: number;
  cpuUtilization: number;
  memoryUtilization: number;
}

const snapshots: MetricSnapshot[] = [
  { apiP95Ms: 118, apiP99Ms: 204, cacheHitRate: 92.6, errorRate: 0.3, queueDepth: 42, cpuUtilization: 41, memoryUtilization: 58 },
  { apiP95Ms: 143, apiP99Ms: 235, cacheHitRate: 90.8, errorRate: 0.5, queueDepth: 67, cpuUtilization: 47, memoryUtilization: 61 },
  { apiP95Ms: 156, apiP99Ms: 262, cacheHitRate: 89.2, errorRate: 0.9, queueDepth: 91, cpuUtilization: 55, memoryUtilization: 68 },
  { apiP95Ms: 131, apiP99Ms: 218, cacheHitRate: 93.4, errorRate: 0.2, queueDepth: 38, cpuUtilization: 39, memoryUtilization: 56 },
];

function getHealth(snapshot: MetricSnapshot): HealthState {
  if (snapshot.errorRate > 1 || snapshot.apiP99Ms > 300 || snapshot.cpuUtilization > 85) return "critical";
  if (snapshot.errorRate > 0.5 || snapshot.apiP95Ms > 150 || snapshot.cpuUtilization > 70) return "degraded";
  return "healthy";
}

export default function DashboardPage() {
  const [index, setIndex] = useState(0);
  const current = snapshots[index];
  const health = getHealth(current);

  const trend = useMemo(() => {
    const previous = snapshots[Math.max(0, index - 1)];
    return {
      latencyDelta: current.apiP95Ms - previous.apiP95Ms,
      cacheDelta: Number((current.cacheHitRate - previous.cacheHitRate).toFixed(1)),
    };
  }, [index, current]);

  const healthColor =
    health === "healthy"
      ? "text-terminal-green border-terminal-green/40 bg-terminal-green/10"
      : health === "degraded"
        ? "text-terminal-cyan border-terminal-cyan/40 bg-terminal-cyan/10"
        : "text-terminal-danger border-terminal-danger/40 bg-terminal-danger/10";

  return (
    <main className="min-h-screen bg-terminal-black p-8 text-terminal-green font-terminal-mono">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="space-y-3">
          <p className="text-xs tracking-[0.2em] text-terminal-gray">[PERFORMANCE_DASHBOARD]</p>
          <h1 className="text-3xl">API Latency, Cache, and System Health</h1>
          <p className="text-sm text-terminal-gray">
            Snapshot viewer for key operational metrics. Use the controls to inspect recent intervals.
          </p>
        </header>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="API P95" value={`${current.apiP95Ms} ms`} hint={`${trend.latencyDelta >= 0 ? "+" : ""}${trend.latencyDelta} ms vs prev`} />
          <MetricCard label="API P99" value={`${current.apiP99Ms} ms`} hint="tail latency" />
          <MetricCard label="Cache Hit Rate" value={`${current.cacheHitRate}%`} hint={`${trend.cacheDelta >= 0 ? "+" : ""}${trend.cacheDelta}% vs prev`} />
          <MetricCard label="Error Rate" value={`${current.errorRate}%`} hint="5xx / total requests" />
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <MetricCard label="Queue Depth" value={String(current.queueDepth)} hint="pending jobs" />
          <MetricCard label="CPU Utilization" value={`${current.cpuUtilization}%`} hint="backend workers" />
          <MetricCard label="Memory Utilization" value={`${current.memoryUtilization}%`} hint="postgres + api" />
        </section>

        <section className="rounded border border-terminal-green/20 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm text-terminal-gray">System Health</h2>
            <span className={`rounded border px-2 py-1 text-xs uppercase ${healthColor}`}>{health}</span>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3 text-xs text-terminal-gray">
            <p>Latency SLO: p95 &lt; 150ms</p>
            <p>Availability SLO: error rate &lt; 0.5%</p>
            <p>Capacity SLO: CPU &lt; 70%</p>
          </div>
        </section>

        <section className="flex gap-2">
          {snapshots.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIndex(i)}
              className={`rounded border px-3 py-1 text-xs ${index === i ? "border-terminal-green text-terminal-green" : "border-terminal-gray/40 text-terminal-gray"}`}
            >
              Snapshot {i + 1}
            </button>
          ))}
        </section>
      </div>
    </main>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <article className="rounded border border-terminal-green/20 bg-black/30 p-4">
      <p className="text-xs text-terminal-gray">{label}</p>
      <p className="mt-2 text-2xl">{value}</p>
      <p className="mt-1 text-xs text-terminal-cyan">{hint}</p>
    </article>
  );
}
