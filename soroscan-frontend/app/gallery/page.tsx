import TerminalGallery from "@/components/terminal/examples/TerminalGallery";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Gallery | SoroScan",
  description:
    "Gallery of SoroScan terminal-style UI components and usage examples.",
};

export default function GalleryPage() {
  return <TerminalGallery />;
}
