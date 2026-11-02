import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { XgTimeline } from "@/components/charts/client";
import { ScoreGrid } from "@/components/charts/score-grid";
import { ShotMap } from "@/components/charts/shot-map";
import { ProbBar } from "@/components/prob-bar";
import { Badge, Card, Stat } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { SITE } from "@/lib/config";
import { getMatch, getMatchPlayers, getMatchPrediction, getMatchShots, type Shot } from "@/lib/data";
import { kickoff, num, pct } from "@/lib/format";
import { leagueById } from "@/lib/leagues";
import { cumulativeXg } from "@/lib/metrics";

export async function generateMetadata({ params }: PageProps<"/match/[id]">): Promise<Metadata> {
  const m = await getMatch(Number((await params).id));
  return m ? { title: `${m.home_team} v ${m.away_team}`, description: `Prediction, shot map and xG timeline for ${m.home_team} v ${m.away_team} (${m.league_name}).` } : {};
}

const BIG_CHANCE_XG = 0.3;

function sideStats(shots: Shot[], side: "h" | "a") {
  const s = shots.filter((x) => x.side === side && x.result !== "OwnGoal");
  return {
    shots: s.length,
    onTarget: s.filter((x) => x.is_goal || x.result === "SavedShot").length,
    bigChances: s.filter((x) => (x.xg ?? 0) >= BIG_CHANCE_XG).length,
    npxg: s.filter((x) => x.situation !== "Penalty").reduce((a, x) => a + (x.xg ?? 0), 0),
  };
}

async function MatchContent({ params }: { params: PageProps<"/match/[id]">["params"] }) {
  const id = Number((await params).id);
  if (!Number.isFinite(id)) notFound();
  const [m, shots, preds, players] = await Promise.all([getMatch(id), getMatchShots(id), getMatchPrediction(id), getMatchPlayers(id)]);
  if (!m) notFound();
  const league = leagueById(m.league_id);
  const ens = preds.find((p) => p.model === "ensemble");
  const finished = m.status === "finished";
  const actualIdx = m.result === "H" ? 0 : m.result === "D" ? 1 : m.result === "A" ? 2 : null;
  const probs = ens ? [ens.p_home, ens.p_draw, ens.p_away] : null;
  const h = sideStats(shots, "h");
  const a = sideStats(shots, "a");
  const timeline = cumulativeXg(shots.filter((s) => s.result !== "OwnGoal").map((s) => ({ minute: s.minute, xg: s.xg, side: s.side, is_goal: s.is_goal })));

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface-1 p-5">
        <div className="mb-2 text-sm text-fg-3">
          {league && <Link href={`/league/${league.slug}/${m.season_id}`} className="hover:underline">{m.league_name}</Link>} · {m.season_label} · {kickoff(m.kickoff_utc)} IST
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <Link href={`/team/${m.home_team_id}`} className="text-right text-lg font-semibold text-fg hover:underline sm:text-2xl">{m.home_team}</Link>
          <div className="text-center">
            <div className="tabular text-3xl font-bold text-fg sm:text-4xl">{finished ? `${m.home_goals} – ${m.away_goals}` : "v"}</div>
            {finished && <div className="tabular text-sm text-fg-2">xG {num(m.home_xg)} – {num(m.away_xg)}</div>}
          </div>
          <Link href={`/team/${m.away_team_id}`} className="text-lg font-semibold text-fg hover:underline sm:text-2xl">{m.away_team}</Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={finished ? "Prediction vs actual" : "Prediction"} subtitle={ens ? `Ensemble model, made ${kickoff(ens.created_utc)} IST (before kickoff)` : undefined}>
          {probs ? (
            <div className="space-y-4">
              <ProbBar home={probs[0]} draw={probs[1]} away={probs[2]} />
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Most likely score" value={ens!.top_score} />
                <Stat label="Expected goals" value={`${num(ens!.exp_home_goals, 1)} – ${num(ens!.exp_away_goals, 1)}`} />
                <Stat label={finished ? "P(actual result)" : "Favourite"} value={finished && actualIdx != null ? pct(probs[actualIdx]) : pct(Math.max(...probs))} />
              </div>
              {finished && actualIdx != null && (
                <p className="text-sm text-fg-2">
                  Result: <Badge tone={probs[actualIdx] === Math.max(...probs) ? "good" : "critical"}>{probs[actualIdx] === Math.max(...probs) ? "model favourite" : "against the model favourite"}</Badge>
                </p>
              )}
              {ens!.score_grid && <ScoreGrid grid={ens!.score_grid} max={SITE.scoreGridMaxGoals} home={m.home_team} away={m.away_team} />}
            </div>
          ) : <p className="text-sm text-fg-3">No pre-kickoff prediction was stored for this match (predictions started when PitchIQ went live).</p>}
        </Card>
        <Card title="Key stats" subtitle="PitchIQ xG; Understat's own xG for comparison">
          {shots.length ? (
            <Table>
              <thead><tr><Th className="text-right">{m.home_team}</Th><Th className="text-center"> </Th><Th>{m.away_team}</Th></tr></thead>
              <tbody>
                {[
                  ["Shots", h.shots, a.shots],
                  ["On target", h.onTarget, a.onTarget],
                  ["Big chances (xG ≥ 0.3)", h.bigChances, a.bigChances],
                  ["xG (PitchIQ)", num(m.home_xg), num(m.away_xg)],
                  ["Non-penalty xG", num(h.npxg), num(a.npxg)],
                  ["xG (Understat)", num(m.home_xg_understat), num(m.away_xg_understat)],
                ].map(([label, hv, av]) => (
                  <tr key={String(label)}><Td className="text-right font-medium">{hv}</Td><Td className="text-center text-xs text-fg-3">{label}</Td><Td className="font-medium">{av}</Td></tr>
                ))}
              </tbody>
            </Table>
          ) : <p className="text-sm text-fg-3">Shot data appears after full time.</p>}
        </Card>
      </div>

      {shots.length > 0 && (
        <>
          <Card title="Shot map"><ShotMap shots={shots} homeTeam={m.home_team} awayTeam={m.away_team} /></Card>
          <Card title="Cumulative xG"><XgTimeline points={timeline} home={m.home_team} away={m.away_team} /></Card>
          <Card title="Players" subtitle="Ordered by xG (Understat player match stats)">
            <Table>
              <thead><tr><Th>Player</Th><Th>Team</Th><Th className="text-right">Min</Th><Th className="text-right">G</Th><Th className="text-right">A</Th><Th className="text-right">Shots</Th><Th className="text-right">xG</Th><Th className="text-right">xA</Th></tr></thead>
              <tbody>
                {players.filter((p) => p.minutes > 0).map((p) => (
                  <tr key={p.player_id}>
                    <Td><Link href={`/player/${p.player_id}`} className="hover:underline">{p.player}</Link></Td>
                    <Td className="text-fg-2">{p.team_id === m.home_team_id ? m.home_team : m.away_team}</Td>
                    <Td className="text-right">{p.minutes}</Td><Td className="text-right">{p.goals}</Td><Td className="text-right">{p.assists}</Td>
                    <Td className="text-right">{p.shots}</Td><Td className="text-right">{num(p.xg)}</Td><Td className="text-right">{num(p.xa)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}

export default function MatchPage(props: PageProps<"/match/[id]">) {
  return (
    <Suspense fallback={<div className="h-96 animate-pulse rounded-xl bg-surface-1" />}>
      <MatchContent params={props.params} />
    </Suspense>
  );
}
