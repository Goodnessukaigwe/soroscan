import { Suspense } from "react";
import OrganizationPage from "./OrganizationPageClient";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Organization | SoroScan",
  description:
    "Manage your SoroScan organization, its members, and its tracked contracts.",
};

export default function OrganizationRoute() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-terminal-black p-6 font-terminal-mono text-terminal-green">
          <div className="mx-auto max-w-6xl animate-terminal-pulse border border-terminal-green/30 p-8">
            Loading organization…
          </div>
        </main>
      }
    >
      <OrganizationPage />
    </Suspense>
  );
}
