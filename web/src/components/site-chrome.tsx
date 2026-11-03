import Link from "next/link";
import { Suspense } from "react";
import { getFreshness } from "@/lib/data";
import { LEAGUES } from "@/lib/leagues";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface-1/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href="/" className="py-1.5 text-lg font-bold tracking-tight text-fg">
          Pitch<span className="text-accent-strong">IQ</span>
        </Link>
        <nav className="flex flex-1 flex-wrap items-center gap-x-4 gap-y-1 text-sm text-fg-2">
          {LEAGUES.map((l) => (
            <Link key={l.id} href={`/league/${l.slug}`} className="hover:text-fg">{l.name}</Link>
          ))}
          <span className="hidden h-4 w-px bg-border sm:inline-block" />
          <Link href="/scout" className="hover:text-fg">Scout</Link>
          <Link href="/ask" className="hover:text-fg">Ask</Link>
          <Link href="/model" className="hover:text-fg">Model</Link>
          <Link href="/about" className="hover:text-fg">About</Link>
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}

async function FreshnessLine() {
  const f = await getFreshness();
  if (!f) return <span>Data pipeline has not published yet.</span>;
  const latest = Object.values(f.leagues)
    .map((l) => l.latest_finished_match_utc)
    .filter(Boolean)
    .sort()
    .at(-1);
  return (
    <span>
      Updated: {f.generated_display}
      {latest && <> · latest match included: {new Date(latest).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</>}
      {Object.values(f.sources).some((s) => !s.ok) && <> · some sources failed on the last run, showing last good data</>}
    </span>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-border bg-surface-1">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-fg-3 sm:flex-row sm:justify-between">
        <Suspense fallback={<span>Loading data status…</span>}>
          <FreshnessLine />
        </Suspense>
        <span>
          Data: Understat, football-data.co.uk, ClubElo, FBref · <Link href="/about" className="underline">sources &amp; methodology</Link> · Not betting advice.
        </span>
      </div>
    </footer>
  );
}
