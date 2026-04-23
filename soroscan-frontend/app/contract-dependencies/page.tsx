"use client";

import { useMemo, useState } from "react";

interface Edge {
  from: string;
  to: string;
  calls: number;
}

const edges: Edge[] = [
  { from: "Router", to: "Vault", calls: 1820 },
  { from: "Router", to: "Oracle", calls: 910 },
  { from: "Vault", to: "Token", calls: 2210 },
  { from: "Vault", to: "FeeCollector", calls: 640 },
  { from: "FeeCollector", to: "Treasury", calls: 620 },
  { from: "Oracle", to: "PriceFeed", calls: 905 },
];

const nodes = Array.from(new Set(edges.flatMap((edge) => [edge.from, edge.to])));

export default function ContractDependenciesPage() {
  const [selected, setSelected] = useState<string>("Router");

  const related = useMemo(
    () => edges.filter((edge) => edge.from === selected || edge.to === selected),
    [selected],
  );

  return (
    <main className="min-h-screen bg-terminal-black p-8 text-terminal-green font-terminal-mono">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <p className="text-xs text-terminal-gray tracking-[0.2em]">[INTERACTIVE_DEPENDENCY_GRAPH]</p>
          <h1 className="text-3xl mt-2">Contract Call Dependency Explorer</h1>
          <p className="text-sm text-terminal-gray mt-2">
            Select a contract to inspect inbound and outbound calls in the graph.
          </p>
        </header>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <aside className="rounded border border-terminal-green/20 p-4 lg:col-span-1">
            <h2 className="text-sm text-terminal-gray mb-3">Contracts</h2>
            <div className="space-y-2">
              {nodes.map((node) => (
                <button
                  key={node}
                  type="button"
                  onClick={() => setSelected(node)}
                  className={`w-full rounded border px-3 py-2 text-left text-sm ${selected === node ? "border-terminal-green bg-terminal-green/10" : "border-terminal-gray/40 text-terminal-gray"}`}
                >
                  {node}
                </button>
              ))}
            </div>
          </aside>

          <div className="rounded border border-terminal-green/20 p-4 lg:col-span-2">
            <h2 className="text-sm text-terminal-gray mb-3">Graph View</h2>
            <div className="rounded border border-terminal-green/10 bg-black/40 p-4">
              {related.length === 0 ? (
                <p className="text-terminal-gray text-sm">No dependencies found for `{selected}`.</p>
              ) : (
                <div className="space-y-3">
                  {related.map((edge) => (
                    <div
                      key={`${edge.from}-${edge.to}`}
                      className="flex items-center justify-between rounded border border-terminal-cyan/30 bg-terminal-cyan/5 px-3 py-2 text-sm"
                    >
                      <span>{edge.from}</span>
                      <span className="text-terminal-cyan">--({edge.calls})--&gt;</span>
                      <span>{edge.to}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
