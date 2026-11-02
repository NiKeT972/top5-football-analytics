"use client";

import Link from "next/link";
import { useState } from "react";
import { PercentileRadar } from "./charts/client";

interface Result { player_id: number; player: string; team: string; league: string; age: number | null; minutes: number; similarity: number }

/** Result list with a radar that overlays the selected candidate on the target player. */
export function ScoutResults({ target, results, metrics, pct }: {
  target: { id: number; name: string }; results: Result[]; metrics: string[]; pct: Record<number, Record<string, number>>;
}) {
  const [sel, setSel] = useState(results[0]?.player_id);
  const chosen = results.find((r) => r.player_id === sel);
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
      <div className="overflow-x-auto">
        <table className="w-full text-sm tabular">
          <thead>
            <tr className="text-left text-xs text-fg-3">
              <th className="border-b border-border px-2 py-2">Player</th><th className="border-b border-border px-2">Team</th>
              <th className="border-b border-border px-2 text-right">Age</th><th className="border-b border-border px-2 text-right">Min</th>
              <th className="border-b border-border px-2 text-right">Similarity</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.player_id} onClick={() => setSel(r.player_id)} className={`cursor-pointer ${r.player_id === sel ? "bg-accent/10" : "hover:bg-surface-2"}`} aria-selected={r.player_id === sel}>
                <td className="border-b border-border/60 px-2 py-1.5"><Link href={`/player/${r.player_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{r.player}</Link></td>
                <td className="border-b border-border/60 px-2 text-fg-2">{r.team} · {r.league}</td>
                <td className="border-b border-border/60 px-2 text-right">{r.age != null ? Math.floor(r.age) : "–"}</td>
                <td className="border-b border-border/60 px-2 text-right">{r.minutes}</td>
                <td className="border-b border-border/60 px-2 text-right font-semibold">{(r.similarity * 100).toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-fg-3">Click a row to overlay that player on the radar.</p>
      </div>
      <div>
        <PercentileRadar metrics={metrics} a={{ name: target.name, values: pct[target.id] ?? {} }} b={chosen ? { name: chosen.player, values: pct[chosen.player_id] ?? {} } : undefined} />
      </div>
    </div>
  );
}
