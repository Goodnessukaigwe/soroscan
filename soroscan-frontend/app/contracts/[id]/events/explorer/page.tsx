import { EventExplorerView } from "@/components/ingest/EventExplorerView";
import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return {
    title: "Contract Events Explorer | SoroScan",
    description: `Browse, filter, and analyze indexed events for contract ${id}.`,
  };
}

export default async function ContractExplorerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EventExplorerView contractId={id} />;
}
