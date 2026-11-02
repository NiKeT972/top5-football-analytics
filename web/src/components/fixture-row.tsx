import Link from "next/link";
import type { Fixture } from "@/lib/data";
import { kickoff, num } from "@/lib/format";
import { ProbBar } from "./prob-bar";
import { Badge } from "./ui/card";

export function FixtureRow({ f }: { f: Fixture }) {
  return (
    <Link href={`/match/${f.match_id}`} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 rounded-lg px-3 py-2.5 hover:bg-surface-2 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <div className="font-medium text-fg sm:truncate">
          <span className="block sm:inline">{f.home_team}</span> <span className="hidden text-fg-3 sm:inline">v</span>{" "}
          <span className="block sm:inline">{f.away_team}</span>
        </div>
        <div className="text-xs text-fg-3">{kickoff(f.kickoff_utc)} IST{f.upset_alert && <> · <Badge tone="critical">Upset alert</Badge></>}</div>
      </div>
      <div className="col-span-2 row-start-2 sm:col-span-1 sm:row-start-auto">
        {f.p_home != null ? <ProbBar home={f.p_home} draw={f.p_draw!} away={f.p_away!} /> : <span className="text-xs text-fg-3">Prediction pending</span>}
      </div>
      <div className="text-right text-sm tabular">
        <div className="font-semibold text-fg">{f.top_score ?? "–"}</div>
        {f.exp_home_goals != null && <div className="text-xs text-fg-3">xG {num(f.exp_home_goals, 1)}–{num(f.exp_away_goals, 1)}</div>}
      </div>
    </Link>
  );
}
