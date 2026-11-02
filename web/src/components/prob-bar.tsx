import { pct } from "@/lib/format";

/** Stacked home / draw / away probability bar with direct labels. */
export function ProbBar({ home, draw, away, labels = true }: { home: number; draw: number; away: number; labels?: boolean }) {
  const parts = [
    { key: "H", p: home, color: "var(--home)", label: "Home" },
    { key: "D", p: draw, color: "var(--draw)", label: "Draw" },
    { key: "A", p: away, color: "var(--away)", label: "Away" },
  ];
  return (
    <div>
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded" role="img" aria-label={`Home ${pct(home)}, draw ${pct(draw)}, away ${pct(away)}`}>
        {parts.map((s) => (
          <div key={s.key} title={`${s.label} ${pct(s.p, 1)}`} style={{ width: `${s.p * 100}%`, background: s.color }} className="first:rounded-l last:rounded-r" />
        ))}
      </div>
      {labels && (
        <div className="mt-1 flex justify-between text-xs tabular text-fg-2">
          <span>{pct(home)}</span>
          <span>{pct(draw)}</span>
          <span>{pct(away)}</span>
        </div>
      )}
    </div>
  );
}
