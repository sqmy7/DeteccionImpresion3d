import type { ReactNode } from "react";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "danger" | "info";

const TONES: Record<Tone, string> = {
  neutral: "border-line bg-surface-2 text-muted",
  accent: "border-accent/40 bg-accent/10 text-accent-fg",
  ok: "border-ok/40 bg-ok/10 text-ok-fg",
  warn: "border-warn/40 bg-warn/10 text-warn-fg",
  danger: "border-danger/50 bg-danger/10 text-danger-fg",
  info: "border-info/50 bg-info/15 text-info-fg",
};

const DOTS: Record<Tone, string> = {
  neutral: "bg-faint",
  accent: "bg-accent",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
};

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  children,
  title,
  className = "",
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex max-w-full items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5 shrink-0">
          {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOTS[tone]}`} />}
          <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${DOTS[tone]}`} />
        </span>
      )}
      <span className="truncate">{children}</span>
    </span>
  );
}
