/** Small pure helpers used by pages (unit-tested). */

export interface TeamMatchRow {
  kickoff_utc: string;
  xg_for: number | null;
  xg_against: number | null;
  goals_for: number;
  goals_against: number;
}

/** Trailing mean over the last `window` rows (rows must be sorted by date). */
export function rolling(values: (number | null)[], window: number): (number | null)[] {
  return values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - window + 1), i + 1).filter((v): v is number => v != null);
    return slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
  });
}

export interface ShotLike {
  minute: number;
  xg: number | null;
  side: "h" | "a";
  is_goal: boolean;
}

/** Step series of cumulative xG per side, one point per shot (plus start and end). */
export function cumulativeXg(shots: ShotLike[], endMinute = 90) {
  const sorted = [...shots].sort((a, b) => a.minute - b.minute);
  let h = 0;
  let a = 0;
  const points: { minute: number; home: number; away: number; goal?: "h" | "a" }[] = [{ minute: 0, home: 0, away: 0 }];
  for (const s of sorted) {
    if (s.side === "h") h += s.xg ?? 0;
    else a += s.xg ?? 0;
    points.push({ minute: s.minute, home: round(h), away: round(a), goal: s.is_goal ? s.side : undefined });
  }
  points.push({ minute: Math.max(endMinute, sorted.at(-1)?.minute ?? 0), home: round(h), away: round(a) });
  return points;
}

const round = (x: number) => Math.round(x * 1000) / 1000;

/** Outcome index from goals: 0 home win, 1 draw, 2 away win. */
export function outcomeIndex(home: number, away: number): 0 | 1 | 2 {
  return home > away ? 0 : home === away ? 1 : 2;
}

/** Ranked probability score for a [home, draw, away] forecast. */
export function rps(p: [number, number, number], outcome: 0 | 1 | 2): number {
  const o = [0, 0, 0];
  o[outcome] = 1;
  const c1 = p[0] - o[0];
  const c2 = p[0] + p[1] - (o[0] + o[1]);
  return (c1 * c1 + c2 * c2) / 2;
}

/** Mean of a numeric field, ignoring nulls. */
export function mean(xs: (number | null | undefined)[]): number | null {
  const v = xs.filter((x): x is number => x != null && !Number.isNaN(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** Running totals of goals and xG over a player's matches (sorted by date). */
export function cumulativeGoalsXg(matches: { kickoff_utc: string; goals: number; xg: number }[]) {
  return matches.reduce<{ date: string; goals: number; xg: number }[]>((acc, m) => {
    const prev = acc.at(-1) ?? { goals: 0, xg: 0 };
    acc.push({ date: m.kickoff_utc, goals: prev.goals + m.goals, xg: Math.round((prev.xg + m.xg) * 100) / 100 });
    return acc;
  }, []);
}
