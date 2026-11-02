import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { MultiLine, PercentileRadar } from "@/components/charts/client";
import { Badge, Card, PageHeader, Stat } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { METRIC_LABEL, SITE } from "@/lib/config";
import { getPercentiles, getPlayerMatches, getPlayerSeasons, getSimilar } from "@/lib/data";
import { num, POSITION_LABEL } from "@/lib/format";
import { leagueById } from "@/lib/leagues";
import { cumulativeGoalsXg } from "@/lib/metrics";

export async function generateMetadata({ params }: PageProps<"/player/[id]">): Promise<Metadata> {
  const s = await getPlayerSeasons(Number((await params).id));
  return s[0] ? { title: s[0].player, description: `${s[0].player}: per-90 percentile radar, xG vs goals and the most similar players.` } : {};
}

async function PlayerContent({ params }: { params: PageProps<"/player/[id]">["params"] }) {
  const id = Number((await params).id);
  if (!Number.isFinite(id)) notFound();
  const seasons = await getPlayerSeasons(id);
  if (!seasons.length) notFound();
  const cur = seasons[0];
  const [pcts, similar, matches] = await Promise.all([getPercentiles([id], cur.season_id), getSimilar(id, cur.season_id), getPlayerMatches(id)]);
  const metrics = SITE.radarMetrics.filter((m) => pcts.some((p) => p.metric === m));
  const values = Object.fromEntries(pcts.map((p) => [METRIC_LABEL[p.metric] ?? p.metric, p.percentile]));
  const cum = cumulativeGoalsXg(matches);

  return (
    <div className="space-y-6">
      <PageHeader title={cur.player} subtitle={<>{cur.team && cur.team_id ? <Link href={`/team/${cur.team_id}`} className="hover:underline">{cur.team}</Link> : cur.team_names} · {leagueById(cur.league_id)?.name} · {cur.position_group ? POSITION_LABEL[cur.position_group] : "position unknown"}{cur.age != null && <> · age {Math.floor(cur.age)}</>}{cur.nation && <> · {cur.nation}</>}</>}>
        <Link href={`/scout?player=${id}&season=${cur.season_id}`} className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white">Find similar players</Link>
      </PageHeader>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
        <Stat label="Minutes" value={cur.minutes} hint={cur.season_label} />
        <Stat label="Goals" value={cur.goals} />
        <Stat label="xG" value={num(cur.xg, 1)} hint={`${num(cur.goals_minus_xg, 1)} vs xG`} />
        <Stat label="Assists" value={cur.assists} />
        <Stat label="xA" value={num(cur.xa, 1)} />
        <Stat label="npxG / 90" value={num(cur.npxg_per90, 2)} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Per-90 percentiles" subtitle={`Vs ${cur.position_group ?? ""} players with ≥ ${SITE.scoutDefaultMinMinutes} minutes, all five leagues`}>
          {metrics.length ? <PercentileRadar metrics={metrics.map((m) => METRIC_LABEL[m] ?? m)} a={{ name: cur.player, values }} /> : <p className="text-sm text-fg-3">Percentiles need at least {SITE.scoutDefaultMinMinutes} minutes (goalkeepers are not profiled: free data has no goalkeeping metrics).</p>}
          <p className="mt-2 text-xs text-fg-3">Free data is attacking-heavy: defensive work (tackles, interceptions) is not captured, so defenders are compared mostly on build-up and chance involvement.</p>
        </Card>
        <Card title="Goals vs xG over time" subtitle="Cumulative, all seasons in the database">
          {cum.length ? <MultiLine data={cum} x="date" series={[{ key: "goals", name: "Goals" }, { key: "xg", name: "xG" }]} /> : <p className="text-sm text-fg-3">No match data.</p>}
        </Card>
      </div>
      <Card title="Most similar players" subtitle="Same season and position group; cosine similarity of standardised per-90 profiles">
        {similar.length ? (
          <Table>
            <thead><tr><Th>#</Th><Th>Player</Th><Th>League</Th><Th className="text-right">Similarity</Th></tr></thead>
            <tbody>
              {similar.map((s) => (
                <tr key={s.other_player_id}>
                  <Td className="text-fg-3">{s.rank}</Td>
                  <Td><Link href={`/player/${s.other_player_id}`} className="hover:underline">{s.other_player}</Link></Td>
                  <Td className="text-fg-2">{leagueById(s.other_league_id)?.name}</Td>
                  <Td className="text-right"><Badge tone="accent">{num(s.similarity * 100, 0)}</Badge></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : <p className="text-sm text-fg-3">Not enough minutes this season to profile.</p>}
      </Card>
      <Card title="Season by season">
        <Table>
          <thead><tr><Th>Season</Th><Th>Team</Th><Th className="text-right">Min</Th><Th className="text-right">G</Th><Th className="text-right">xG</Th><Th className="text-right">A</Th><Th className="text-right">xA</Th><Th className="text-right">npxG/90</Th><Th className="text-right">xA/90</Th></tr></thead>
          <tbody>
            {seasons.map((s) => (
              <tr key={`${s.season_id}-${s.league_id}`}>
                <Td>{s.season_label}</Td><Td className="text-fg-2">{s.team ?? s.team_names}</Td><Td className="text-right">{s.minutes}</Td>
                <Td className="text-right">{s.goals}</Td><Td className="text-right">{num(s.xg, 1)}</Td><Td className="text-right">{s.assists}</Td>
                <Td className="text-right">{num(s.xa, 1)}</Td><Td className="text-right">{num(s.npxg_per90)}</Td><Td className="text-right">{num(s.xa_per90)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}

export default function PlayerPage(props: PageProps<"/player/[id]">) {
  return <Suspense fallback={<div className="h-96 animate-pulse rounded-xl bg-surface-1" />}><PlayerContent params={props.params} /></Suspense>;
}
