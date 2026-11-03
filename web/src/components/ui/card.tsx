import clsx from "clsx";
import type { ReactNode } from "react";

export function Card({ title, subtitle, action, children, className }: {
  title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={clsx("min-w-0 rounded-xl border border-border bg-surface-1 p-4 sm:p-5", className)}>
      {(title || action) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold text-fg">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-fg-2">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "good" | "critical" }) {
  const tones = {
    neutral: "bg-surface-2 text-fg-2",
    accent: "bg-accent/15 text-accent-strong",
    good: "bg-good/15 text-good",
    critical: "bg-critical/15 text-critical",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <div className="text-xs text-fg-3">{label}</div>
      <div className="tabular text-lg font-semibold text-fg">{value}</div>
      {hint && <div className="text-xs text-fg-3">{hint}</div>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-surface-1 p-8 text-center">
      <p className="font-medium text-fg">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-prose text-sm text-fg-2">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-fg-2">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
