import { TimelineView } from "@/components/ingest/TimelineView";
import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return {
    title: "Contract Timeline | SoroScan",
    description: `Chronological timeline of indexed events for contract ${id}.`,
  };
}

export default async function ContractTimelinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <TimelineView contractId={id} />;
}
