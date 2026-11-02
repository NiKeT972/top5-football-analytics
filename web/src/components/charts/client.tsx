"use client";

/**
 * Interactive charts (Recharts). Colours come from CSS variables so light/dark mode
 * switch with the theme; every chart has a tooltip, legends for >= 2 series, and one y-axis.
 */
import { useMemo, useState } from "react";
import {
  CartesianGrid, LabelList, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";

const axis = { stroke: "var(--text-muted)", fontSize: 11, tickLine: false } as const;
const grid = <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />;
const tooltipStyle = {
  contentStyle: { background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--text-primary)" },
  labelStyle: { color: "var(--text-secondary)" },
} as const;
const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

// ------------------------------------------------------------------ Elo (highlight one of many)
export function EloChart({ series }: { series: { team_id: string; team: string; points: { t: number; elo: number }[] }[] }) {
  const [focus, setFocus] = useState(series[0]?.team_id ?? "");
  const data = useMemo(() => {
    const ts = [...new Set(series.flatMap((s) => s.points.map((p) => p.t)))].sort((a, b) => a - b);
    const lookup = series.map((s) => ({ id: s.team_id, pts: s.points }));
    return ts.map((t) => {
      const row: Record<string, number> = { t };
      for (const s of lookup) {
        const last = s.pts.filter((p) => p.t <= t).at(-1);
        if (last) row[s.id] = Math.round(last.elo);
      }
      return row;
    });
  }, [series]);
  if (!series.length) return null;
  const focused = series.find((s) => s.team_id === focus);
  return (
    <div>
      <label className="mb-2 flex items-center gap-2 text-sm text-fg-2">
        Highlight
        <select value={focus} onChange={(e) => setFocus(e.target.value)} className="rounded-md border border-border bg-surface-1 px-2 py-1 text-fg">
          {series.map((s) => <option key={s.team_id} value={s.team_id}>{s.team}</option>)}
        </select>
      </label>
      <div className="h-72">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            {grid}
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={(t) => new Date(t).toLocaleDateString("en-GB", { month: "short", year: "2-digit" })} {...axis} />
            <YAxis domain={["auto", "auto"]} {...axis} />
            <Tooltip {...tooltipStyle} labelFormatter={(t) => new Date(Number(t)).toLocaleDateString("en-GB")} formatter={(v, name) => [v, series.find((s) => s.team_id === name)?.team ?? name]} itemSorter={(i) => -(Number(i.value) || 0)} />
            {series.filter((s) => s.team_id !== focus).map((s) => (
              <Line key={s.team_id} dataKey={s.team_id} dot={false} stroke="var(--draw)" strokeOpacity={0.45} strokeWidth={1} isAnimationActive={false} connectNulls type="stepAfter" />
            ))}
            {focused && <Line dataKey={focused.team_id} dot={false} stroke="var(--accent)" strokeWidth={2.5} isAnimationActive={false} connectNulls type="stepAfter" />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-fg-3">Grey: every other club in the league. Ratings from ClubElo.</p>
    </div>
  );
}

// ------------------------------------------------------------------ xG for vs against scatter
export function XgScatter({ points }: { points: { team: string; xgFor: number; xgAgainst: number }[] }) {
  if (!points.length) return null;
  const meanFor = points.reduce((a, p) => a + p.xgFor, 0) / points.length;
  const meanAg = points.reduce((a, p) => a + p.xgAgainst, 0) / points.length;
  return (
    <div className="h-80">
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 28, right: 28, bottom: 18, left: -4 }}>
          <CartesianGrid stroke="var(--border)" />
          <XAxis type="number" dataKey="xgFor" name="xG for / match" domain={["auto", "auto"]} {...axis} label={{ value: "xG for per match →", position: "insideBottom", offset: -10, fill: "var(--text-muted)", fontSize: 11 }} />
          <YAxis type="number" dataKey="xgAgainst" name="xG against / match" domain={["auto", "auto"]} reversed {...axis} label={{ value: "xGA per match (↑ better)", angle: -90, position: "insideLeft", offset: 18, fill: "var(--text-muted)", fontSize: 11 }} />
          <ZAxis range={[70, 70]} />
          <ReferenceLine x={meanFor} stroke="var(--text-muted)" strokeDasharray="3 3" />
          <ReferenceLine y={meanAg} stroke="var(--text-muted)" strokeDasharray="3 3" />
          <Tooltip {...tooltipStyle} formatter={(v) => Number(v).toFixed(2)} labelFormatter={() => ""} />
          <Scatter data={points} fill="var(--accent)" stroke="var(--surface-1)" strokeWidth={2} name="Team" isAnimationActive={false}>
            <LabelList dataKey="team" position="top" fontSize={10} fill="var(--text-secondary)" />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

// ------------------------------------------------------------------ cumulative xG timeline
export function XgTimeline({ points, home, away }: { points: { minute: number; home: number; away: number; goal?: "h" | "a" }[]; home: string; away: string }) {
  return (
    <div className="h-64">
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
          {grid}
          <XAxis dataKey="minute" type="number" domain={[0, "dataMax"]} ticks={[0, 15, 30, 45, 60, 75, 90]} {...axis} />
          <YAxis {...axis} />
          <Tooltip {...tooltipStyle} labelFormatter={(m) => `${m}'`} formatter={(v) => Number(v).toFixed(2)} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="stepAfter" dataKey="home" name={home} stroke="var(--home)" strokeWidth={2} isAnimationActive={false}
            dot={(p: { cx?: number; cy?: number; payload?: { goal?: string }; index?: number }) => p.payload?.goal === "h" ? <circle key={p.index} cx={p.cx} cy={p.cy} r={5} fill="var(--home)" stroke="var(--surface-1)" strokeWidth={2} /> : <g key={p.index} />} />
          <Line type="stepAfter" dataKey="away" name={away} stroke="var(--away)" strokeWidth={2} isAnimationActive={false}
            dot={(p: { cx?: number; cy?: number; payload?: { goal?: string }; index?: number }) => p.payload?.goal === "a" ? <circle key={p.index} cx={p.cx} cy={p.cy} r={5} fill="var(--away)" stroke="var(--surface-1)" strokeWidth={2} /> : <g key={p.index} />} />
        </LineChart>
      </ResponsiveContainer>
      <p className="text-xs text-fg-3">Dots mark goals.</p>
    </div>
  );
}

// ------------------------------------------------------------------ generic multi-line (≤ 4 series)
export function MultiLine({ data, x, series, height = 256, yLabel, xIsDate = true }: {
  data: Record<string, number | string | null>[]; x: string; series: { key: string; name: string }[]; height?: number; yLabel?: string; xIsDate?: boolean;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
          {grid}
          <XAxis dataKey={x} {...axis} tickFormatter={xIsDate ? (t) => new Date(t).toLocaleDateString("en-GB", { month: "short", year: "2-digit" }) : undefined} minTickGap={24} />
          <YAxis {...axis} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", offset: 16, fill: "var(--text-muted)", fontSize: 11 } : undefined} />
          <Tooltip {...tooltipStyle} labelFormatter={xIsDate ? (t) => new Date(String(t)).toLocaleDateString("en-GB") : undefined} formatter={(v) => (v == null ? "–" : Number(v).toFixed(2))} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.slice(0, 4).map((s, i) => (
            <Line key={s.key} dataKey={s.key} name={s.name} stroke={SERIES[i]} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ------------------------------------------------------------------ percentile radar
export function PercentileRadar({ metrics, a, b }: {
  metrics: string[]; a: { name: string; values: Record<string, number> }; b?: { name: string; values: Record<string, number> };
}) {
  const data = metrics.map((m) => ({ metric: m, a: a.values[m] ?? 0, b: b?.values[m] ?? 0 }));
  return (
    <div className="h-80">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis dataKey="metric" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Tooltip {...tooltipStyle} formatter={(v) => `${Number(v).toFixed(0)}th pct`} />
          <Radar name={a.name} dataKey="a" stroke="var(--s1)" fill="var(--s1)" fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} />
          {b && <Radar name={b.name} dataKey="b" stroke="var(--s2)" fill="var(--s2)" fillOpacity={0.15} strokeWidth={2} isAnimationActive={false} />}
          {b && <Legend wrapperStyle={{ fontSize: 12 }} />}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ------------------------------------------------------------------ calibration
export function CalibrationChart({ rows, models }: { rows: { model: string; outcome: string; mean_pred: number; obs_freq: number; n: number }[]; models: { key: string; name: string }[] }) {
  const outcomes = [...new Set(rows.map((r) => r.outcome))];
  const [outcome, setOutcome] = useState(outcomes[0] ?? "");
  const byModel = models.map((m) => ({ ...m, data: rows.filter((r) => r.model === m.key && r.outcome === outcome && r.n >= 20).sort((x, y) => x.mean_pred - y.mean_pred) }));
  return (
    <div>
      {outcomes.length > 1 && (
        <div className="mb-2 flex gap-1" role="tablist">
          {outcomes.map((o) => (
            <button key={o} role="tab" aria-selected={o === outcome} onClick={() => setOutcome(o)} className={`rounded-md px-2.5 py-1 text-xs font-medium ${o === outcome ? "bg-accent text-white" : "bg-surface-2 text-fg-2"}`}>
              P({o})
            </button>
          ))}
        </div>
      )}
      <div className="h-72">
        <ResponsiveContainer>
          <LineChart margin={{ top: 8, right: 16, bottom: 12, left: -8 }}>
            <CartesianGrid stroke="var(--border)" />
            <XAxis type="number" dataKey="mean_pred" domain={[0, 1]} {...axis} label={{ value: "predicted probability", position: "insideBottom", offset: -6, fill: "var(--text-muted)", fontSize: 11 }} />
            <YAxis type="number" domain={[0, 1]} {...axis} />
            <Tooltip {...tooltipStyle} formatter={(v) => Number(v).toFixed(3)} labelFormatter={(v) => `predicted ${Number(v).toFixed(2)}`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line data={[{ mean_pred: 0, obs_freq: 0 }, { mean_pred: 1, obs_freq: 1 }]} dataKey="obs_freq" name="Perfect" stroke="var(--text-muted)" strokeDasharray="4 4" dot={false} isAnimationActive={false} legendType="none" />
            {byModel.map((m, i) => (
              <Line key={m.key} data={m.data} dataKey="obs_freq" name={m.name} stroke={SERIES[i]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
