import type { Shot } from "@/lib/data";
import { num } from "@/lib/format";

const L = 105;
const W = 68;
const ON_TARGET = new Set(["SavedShot", "Goal"]);

function outcome(s: Shot): "goal" | "saved" | "off" {
  if (s.is_goal) return "goal";
  return ON_TARGET.has(s.result) ? "saved" : "off";
}

const STYLE = {
  goal: { fill: "var(--shot-goal)", stroke: "var(--surface-1)", label: "Goal" },
  saved: { fill: "var(--shot-saved)", stroke: "var(--surface-1)", label: "Saved" },
  off: { fill: "none", stroke: "var(--shot-off)", label: "Off target / blocked" },
} as const;

/**
 * Full-pitch shot map: home team attacks right, away team attacks left.
 * Marker area is proportional to xG; colour + fill encode the outcome (with a legend).
 * Each marker has a native tooltip (<title>).
 */
export function ShotMap({ shots, homeTeam, awayTeam }: { shots: Shot[]; homeTeam: string; awayTeam: string }) {
  const pts = shots
    .filter((s) => s.result !== "OwnGoal")
    .map((s) => {
      const home = s.side === "h";
      return { s, x: home ? s.x_m : L - s.x_m, y: home ? W - s.y_m : s.y_m, r: 0.8 + Math.sqrt(s.xg ?? 0.02) * 3.2, o: outcome(s) };
    })
    .sort((a, b) => (a.o === "goal" ? 1 : 0) - (b.o === "goal" ? 1 : 0));
  return (
    <figure>
      <div className="mb-2 flex justify-between text-xs font-medium text-fg-2">
        <span>← {awayTeam} attack</span>
        <span>{homeTeam} attack →</span>
      </div>
      <svg viewBox={`-2 -2 ${L + 4} ${W + 4}`} className="w-full rounded-lg" role="img" aria-label={`Shot map: ${pts.length} shots`}>
        <rect x={-2} y={-2} width={L + 4} height={W + 4} fill="var(--pitch)" />
        <g fill="none" stroke="var(--pitch-line)" strokeWidth={0.35}>
          <rect x={0} y={0} width={L} height={W} />
          <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
          <circle cx={L / 2} cy={W / 2} r={9.15} />
          {[0, L].map((gx) => {
            const dir = gx === 0 ? 1 : -1;
            return (
              <g key={gx}>
                <rect x={gx === 0 ? 0 : L - 16.5} y={W / 2 - 20.16} width={16.5} height={40.32} />
                <rect x={gx === 0 ? 0 : L - 5.5} y={W / 2 - 9.16} width={5.5} height={18.32} />
                <line x1={gx} y1={W / 2 - 3.66} x2={gx} y2={W / 2 + 3.66} strokeWidth={1.2} />
                <circle cx={gx + dir * 11} cy={W / 2} r={0.4} fill="var(--pitch-line)" />
              </g>
            );
          })}
        </g>
        {pts.map(({ s, x, y, r, o }) => (
          <circle key={s.shot_id} cx={x} cy={y} r={r} fill={STYLE[o].fill} fillOpacity={o === "off" ? 0 : 0.9} stroke={STYLE[o].stroke} strokeWidth={o === "off" ? 0.45 : 0.35}>
            <title>{`${s.minute}' ${s.player ?? "Unknown"} (${s.team}) · xG ${num(s.xg)} · ${s.situation} · ${s.shot_type} · ${STYLE[o].label}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-2">
        {(Object.keys(STYLE) as (keyof typeof STYLE)[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="4.5" fill={STYLE[k].fill === "none" ? "none" : STYLE[k].fill} stroke={k === "off" ? STYLE[k].stroke : "none"} strokeWidth={1.5} /></svg>
            {STYLE[k].label}
          </span>
        ))}
        <span>Marker size = xG</span>
      </figcaption>
    </figure>
  );
}
