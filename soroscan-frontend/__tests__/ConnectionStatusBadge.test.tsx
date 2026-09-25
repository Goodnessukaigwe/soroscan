import { render, screen } from "@testing-library/react";

import {
  ConnectionStatusBadge,
  type ConnectionStatus,
} from "@/src/components/ConnectionStatusBadge";

describe("ConnectionStatusBadge", () => {
  it.each([
    ["connected", "Connected", "text-terminal-green", "shadow-[var(--shadow-glow-green)]"],
    [
      "reconnecting",
      "Reconnecting",
      "text-terminal-warning",
      "shadow-[var(--shadow-glow-warning)]",
    ],
    ["offline", "Offline", "text-terminal-danger", "shadow-[var(--shadow-glow-danger)]"],
  ] as const)(
    "renders the %s state with accessible text and glow",
    (status: ConnectionStatus, label, textClass, glowClass) => {
      render(<ConnectionStatusBadge status={status} />);

      const badge = screen.getByRole("status");
      expect(badge).toHaveTextContent(label);
      expect(badge).toHaveAttribute(
        "aria-label",
        expect.stringContaining(label),
      );
      expect(badge).toHaveClass(textClass, glowClass, "transition-all", "duration-300");
      expect(badge).toHaveAttribute("data-status", status);
      expect(screen.getByTestId("connection-status-dot")).toHaveClass(
        "transition-all",
        "duration-300",
      );
    },
  );
});
