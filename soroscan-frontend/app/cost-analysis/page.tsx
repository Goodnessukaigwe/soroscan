"use client";

import { useMemo, useState } from "react";

interface FeePoint {
  date: string;
  txCount: number;
  avgFeeXlm: number;
}

const points: FeePoint[] = [
  { date: "2026-03-20", txCount: 840, avgFeeXlm: 0.00019 },
  { date: "2026-03-21", txCount: 915, avgFeeXlm: 0.00021 },
  { date: "2026-03-22", txCount: 1002, avgFeeXlm: 0.00024 },
  { date: "2026-03-23", txCount: 964, avgFeeXlm: 0.00022 },
  { date: "2026-03-24", txCount: 1108, avgFeeXlm: 0.00026 },
  { date: "2026-03-25", txCount: 1212, avgFeeXlm: 0.00028 },
  { date: "2026-03-26", txCount: 1154, avgFeeXlm: 0.00025 },
];

function toUsd(xlmFee: number, xlmPrice = 0.12): number {
  return Number((xlmFee * xlmPrice).toFixed(6));
}

export default function CostAnalysisPage() {
  const [pricePerXlm, setPricePerXlm] = useState(0.12);

  const summary = useMemo(() => {
    const totalTx = points.reduce((sum, p) => sum + p.txCount, 0);
    const weightedFee = points.reduce((sum, p) => sum + p.avgFeeXlm * p.txCount, 0);
    const blendedFee = weightedFee / totalTx;
    const totalFeeXlm = blendedFee * totalTx;
    const totalFeeUsd = totalFeeXlm * pricePerXlm;
    return { totalTx, blendedFee, totalFeeXlm, totalFeeUsd };
  }, [pricePerXlm]);

  return (
    <main className="min-h-screen bg-terminal-black p-8 text-terminal-green font-terminal-mono">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="space-y-2">
          <p className="text-xs text-terminal-gray tracking-[0.2em]">[COST_ANALYSIS_DASHBOARD]</p>
          <h1 className="text-3xl">Transaction Fee Trends</h1>
          <p className="text-sm text-terminal-gray">Track fee movement, total spend, and transaction volume over time.</p>
        </header>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Tile label="Total Transactions" value={summary.totalTx.toLocaleString()} />
          <Tile label="Weighted Avg Fee" value={`${summary.blendedFee.toFixed(6)} XLM`} />
          <Tile label="Total Fees" value={`${summary.totalFeeXlm.toFixed(3)} XLM`} />
          <Tile label="Total Fees (USD)" value={`$${summary.totalFeeUsd.toFixed(2)}`} />
        </section>

        <section className="rounded border border-terminal-green/20 p-4">
          <label htmlFor="xlm-price" className="block text-xs text-terminal-gray mb-2">
            XLM Price (USD)
          </label>
          <input
            id="xlm-price"
            type="number"
            value={pricePerXlm}
            onChange={(e) => setPricePerXlm(Number(e.target.value) || 0)}
            step="0.01"
            className="rounded border border-terminal-green/30 bg-terminal-black px-3 py-2 text-terminal-green"
          />
        </section>

        <section className="rounded border border-terminal-green/20 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-terminal-green/5">
              <tr>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-right">Tx Count</th>
                <th className="px-3 py-2 text-right">Avg Fee (XLM)</th>
                <th className="px-3 py-2 text-right">Avg Fee (USD)</th>
                <th className="px-3 py-2 text-right">Daily Fee Spend (USD)</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => {
                const avgUsd = toUsd(point.avgFeeXlm, pricePerXlm);
                const dayUsd = avgUsd * point.txCount;
                return (
                  <tr key={point.date} className="border-t border-terminal-green/10">
                    <td className="px-3 py-2">{point.date}</td>
                    <td className="px-3 py-2 text-right">{point.txCount.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right">{point.avgFeeXlm.toFixed(6)}</td>
                    <td className="px-3 py-2 text-right">${avgUsd.toFixed(6)}</td>
                    <td className="px-3 py-2 text-right">${dayUsd.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>
    </main>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded border border-terminal-green/20 bg-black/30 p-4">
      <p className="text-xs text-terminal-gray">{label}</p>
      <p className="mt-2 text-xl">{value}</p>
    </article>
  );
}
