import { redirect } from "next/navigation";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Developer Portal Documentation | SoroScan",
  description:
    "Developer documentation for integrating with the SoroScan API, SDKs, and webhooks.",
};

export default function DocsIndexPage() {
  redirect("/developer-portal/docs/quickstart");
}
