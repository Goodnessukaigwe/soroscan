"use client";

export type ConnectionStatus = "connected" | "reconnecting" | "offline";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  {
    label: string;
    description: string;
    textClass: string;
    dotClass: string;
    glowClass: string;
  }
> = {
  connected: {
    label: "Connected",
    description: "Live event stream is connected.",
    textClass: "text-terminal-green",
    dotClass: "bg-terminal-green",
    glowClass: "shadow-[var(--shadow-glow-green)]",
  },
  reconnecting: {
    label: "Reconnecting",
    description: "Connection interrupted. Attempting to reconnect.",
    textClass: "text-terminal-warning",
    dotClass: "bg-terminal-warning",
    glowClass: "shadow-[var(--shadow-glow-warning)]",
  },
  offline: {
    label: "Offline",
    description: "Live event stream is offline.",
    textClass: "text-terminal-danger",
    dotClass: "bg-terminal-danger",
    glowClass: "shadow-[var(--shadow-glow-danger)]",
  },
};

export function ConnectionStatusBadge({
  status,
  className = "",
}: {
  status: ConnectionStatus;
  className?: string;
}) {
  const config = STATUS_CONFIG[status];

  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={`Connection status: ${config.label}. ${config.description}`}
      title={config.description}
      data-status={status}
      className={[
        "inline-flex items-center gap-1.5 rounded-full border border-current/30",
        "px-2 py-0.5 font-terminal-mono text-xs uppercase tracking-wider",
        "transition-all duration-300 ease-in-out",
        config.textClass,
        config.glowClass,
        className,
      ].join(" ")}
    >
      <span
        aria-hidden="true"
        data-testid="connection-status-dot"
        className={[
          "inline-block h-2 w-2 rounded-full transition-all duration-300 ease-in-out",
          config.dotClass,
          config.glowClass,
          status === "offline" ? "" : "animate-pulse",
        ].join(" ")}
      />
      {config.label}
    </span>
  );
}
