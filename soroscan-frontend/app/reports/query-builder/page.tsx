"use client";

import { useMemo, useState } from "react";

interface EventRow {
  contractId: string;
  eventType: string;
  ledger: number;
  timestamp: string;
  txHash: string;
}

const sourceRows: EventRow[] = [
  { contractId: "CABC1", eventType: "swap", ledger: 520001, timestamp: "2026-03-26T10:12:00Z", txHash: "tx_001" },
  { contractId: "CABC1", eventType: "mint", ledger: 520008, timestamp: "2026-03-26T10:15:00Z", txHash: "tx_002" },
  { contractId: "CXYZ9", eventType: "burn", ledger: 520020, timestamp: "2026-03-26T10:19:00Z", txHash: "tx_003" },
  { contractId: "CXYZ9", eventType: "swap", ledger: 520025, timestamp: "2026-03-26T10:22:00Z", txHash: "tx_004" },
];

const selectableColumns: Array<keyof EventRow> = ["contractId", "eventType", "ledger", "timestamp", "txHash"];

function downloadBlob(content: string, fileName: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export default function QueryBuilderReportPage() {
  const [contractFilter, setContractFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [columns, setColumns] = useState<Array<keyof EventRow>>(selectableColumns);

  const rows = useMemo(() => {
    return sourceRows.filter((row) => {
      const contractMatch = contractFilter ? row.contractId.toLowerCase().includes(contractFilter.toLowerCase()) : true;
      const typeMatch = eventTypeFilter ? row.eventType === eventTypeFilter : true;
      return contractMatch && typeMatch;
    });
  }, [contractFilter, eventTypeFilter]);

  const exportJson = () => {
    const payload = rows.map((row) => pickColumns(row, columns));
    downloadBlob(JSON.stringify(payload, null, 2), "custom-report.json", "application/json");
  };

  const exportCsv = () => {
    const headers = columns.join(",");
    const body = rows
      .map((row) => {
        const values = columns.map((col) => String(row[col]).replaceAll('"', '""'));
        return values.map((value) => `"${value}"`).join(",");
      })
      .join("\n");
    downloadBlob(`${headers}\n${body}`, "custom-report.csv", "text/csv");
  };

  const toggleColumn = (column: keyof EventRow) => {
    setColumns((prev) =>
      prev.includes(column) ? prev.filter((item) => item !== column) : [...prev, column],
    );
  };

  return (
    <main className="min-h-screen bg-terminal-black p-8 text-terminal-green font-terminal-mono">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <p className="text-xs text-terminal-gray tracking-[0.2em]">[QUERY_BUILDER]</p>
          <h1 className="text-3xl mt-2">Custom Data Report Builder</h1>
          <p className="text-sm text-terminal-gray mt-2">
            Build a filtered report and export it as CSV or JSON.
          </p>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-4 rounded border border-terminal-green/20 p-4">
          <input
            value={contractFilter}
            onChange={(e) => setContractFilter(e.target.value)}
            placeholder="Filter by contract"
            className="rounded border border-terminal-green/30 bg-terminal-black px-3 py-2"
          />
          <select
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
            className="rounded border border-terminal-green/30 bg-terminal-black px-3 py-2"
          >
            <option value="">All event types</option>
            <option value="swap">swap</option>
            <option value="mint">mint</option>
            <option value="burn">burn</option>
          </select>
          <div className="flex gap-2">
            <button type="button" onClick={exportCsv} className="rounded border border-terminal-cyan/40 px-3 py-2 text-terminal-cyan">
              Export CSV
            </button>
            <button type="button" onClick={exportJson} className="rounded border border-terminal-green/40 px-3 py-2">
              Export JSON
            </button>
          </div>
        </section>

        <section className="rounded border border-terminal-green/20 p-4">
          <p className="text-xs text-terminal-gray mb-2">Columns</p>
          <div className="flex flex-wrap gap-2">
            {selectableColumns.map((column) => (
              <label key={column} className="inline-flex items-center gap-2 rounded border border-terminal-green/20 px-2 py-1 text-xs">
                <input
                  type="checkbox"
                  checked={columns.includes(column)}
                  onChange={() => toggleColumn(column)}
                />
                {column}
              </label>
            ))}
          </div>
        </section>

        <section className="rounded border border-terminal-green/20 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-terminal-green/5">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-3 py-2 text-left">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.txHash} className="border-t border-terminal-green/10">
                  {columns.map((column) => (
                    <td key={`${row.txHash}-${column}`} className="px-3 py-2">
                      {String(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </main>
  );
}

function pickColumns(row: EventRow, columns: Array<keyof EventRow>): Partial<EventRow> {
  return columns.reduce<Partial<EventRow>>((acc, col) => {
    Object.assign(acc, { [col]: row[col] });
    return acc;
  }, {});
}
