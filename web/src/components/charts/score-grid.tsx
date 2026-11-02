import { pct } from "@/lib/format";

/** Scoreline probability heatmap (rows = home goals, columns = away goals), sequential single hue. */
export function ScoreGrid({ grid, max = 5, home, away }: { grid: number[][]; max?: number; home: string; away: string }) {
  const g = grid.slice(0, max + 1).map((r) => r.slice(0, max + 1));
  const top = Math.max(...g.flat());
  return (
    <div className="overflow-x-auto">
      <table className="text-xs tabular">
        <caption className="mb-1 text-left text-fg-3">Rows: {home} goals · columns: {away} goals</caption>
        <thead>
          <tr>
            <th />
            {g[0].map((_, j) => <th key={j} className="px-1 font-medium text-fg-3">{j}</th>)}
          </tr>
        </thead>
        <tbody>
          {g.map((row, i) => (
            <tr key={i}>
              <th className="pr-1 font-medium text-fg-3">{i}</th>
              {row.map((p, j) => (
                <td key={j} title={`${i}-${j}: ${pct(p, 1)}`} className="h-8 w-10 rounded text-center" style={{ background: `color-mix(in oklab, var(--accent) ${Math.round((p / top) * 85)}%, var(--surface-2))`, color: p / top > 0.55 ? "white" : "var(--text-secondary)" }}>
                  {pct(p, 0)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
