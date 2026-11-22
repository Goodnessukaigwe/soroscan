import PerformanceDashboardPage from "@/app/performance/page";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Performance Dashboard | SoroScan",
  description:
    "Monitor SoroScan indexing performance, latency, and throughput metrics.",
};

export default function DashboardPerformancePage() {
  return <PerformanceDashboardPage />;
}
