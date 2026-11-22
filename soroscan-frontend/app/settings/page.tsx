import { Suspense } from "react";
import SettingsShell from "./SettingsShell";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Settings | SoroScan",
  description:
    "Manage your SoroScan account, organization, and notification settings.",
};

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#0a0e27] text-green-400 p-6 font-mono">
          <div className="mx-auto max-w-5xl space-y-6">
            <div className="rounded-3xl border border-green-500/20 bg-[#061120]/90 p-6 shadow-lg shadow-black/20">
              <div className="h-24 animate-pulse rounded-xl bg-[#08142f]/80"></div>
            </div>
          </div>
        </main>
      }
    >
      <SettingsShell />
    </Suspense>
  );
}
