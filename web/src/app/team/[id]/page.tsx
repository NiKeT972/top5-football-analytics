import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { MultiLine } from "@/components/charts/client";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { SITE } from "@/lib/config";
import { getEloHistory, getTeam, getTeamMatches, getTeamPlayers } from "@/lib/data";
import { dateOnly, num, POSITION_LABEL, seasonLabel } from "@/lib/format";
import { leagueById } from "@/lib/leagues";
import { mean, rolling } from "@/lib/metrics";

export async function generateMetadata({ params }: PageProps<"/team/[id]">): Promise<Metadata> {
  const t = await getTeam((await params).id);
  return t ? { title: t.name, description: `${t.name}: Elo history, rolling xG, home and away splits and top players.` } : {};
}

async function TeamContent({ params }: { params: PageProps<"/team/[id]">["params"] }) {
  const { id } = await params;
  const team = await getTeam(id);
  if (!team) notFound();
  const matches = await getTeamMatches(id);
  const seasonId = matches.at(-1)?.season_id;
  const [elo, players] = await Promise.all([
    getEloHistory([id], matches[0]?.kickoff_utc.slice(0, 10) ?? "2000-01-01"),
    seasonId ? getTeamPlayers(id, seasonId) : Promise.resolve([]),
  ]);
  const league = leagueById(team.league_id);
  if (!matches.length) return <><PageHeader title={team.name} /><EmptyState title="No matches published for this team yet" /></>;

  const w = SITE.rollingWindow;
  const xf = rolling(matches.map((m) => m.xg_for), w);
  const xa = rolling(matches.map((m) => m.xg_against), w);
  const roll = matches.map((m, i) => ({ date: m.kickoff_utc, xgFor: xf[i], xgAgainst: xa[i] })).slice(w - 1);
  const eloSeries = elo.map((e) => ({ date: e.valid_from, elo: Math.round(e.elo) }));
  const season = matches.filter((m) => m.season_id === seasonId);
  const split = (venue: string) => {
    const s = season.filter((m) => m.venue === venue);
    return { n: s.length, ppg: mean(s.map((m) => m.points)), gf: mean(s.map((m) => m.goals_for)), ga: mean(s.map((m) => m.goals_against)), xgf: mean(s.map((m) => m.xg_for)), xga: mean(s.map((m) => m.xg_against)) };
  };
  const home = split("home");
  const away = split("away");

  return (
    <div className="space-y-6">
      <PageHeader title={team.name} subtitle={<>{league ? <Link href={`/league/${league.slug}`} className="hover:underline">{team.league_name}</Link> : team.league_name} · {team.country}</>} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Current Elo" value={eloSeries.at(-1)?.elo ?? "–"} />
        <Stat label={`xG for, last ${w}`} value={num(xf.at(-1), 2)} hint="per match" />
        <Stat label={`xG against, last ${w}`} value={num(xa.at(-1), 2)} hint="per match" />
        <Stat label="Points per game" value={num(mean(season.map((m) => m.points)), 2)} hint={seasonId ? seasonLabel(seasonId) : undefined} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Rolling xG (last ${w} matches)`} subtitle="League matches only">
          <MultiLine data={roll} x="date" series={[{ key: "xgFor", name: "xG for" }, { key: "xgAgainst", name: "xG against" }]} />
        </Card>
        <Card title="Elo over time" subtitle="ClubElo rating">
          {eloSeries.length ? <MultiLine data={eloSeries} x="date" series={[{ key: "elo", name: "Elo" }]} /> : <p className="text-sm text-fg-3">Elo unavailable.</p>}
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Home vs away" subtitle={seasonId ? `${seasonLabel(seasonId)}, per match` : undefined}>
          <Table>
            <thead><tr><Th /><Th className="text-right">Played</Th><Th className="text-right">Pts/G</Th><Th className="text-right">GF</Th><Th className="text-right">GA</Th><Th className="text-right">xGF</Th><Th className="text-right">xGA</Th></tr></thead>
            <tbody>
              {[["Home", home], ["Away", away]].map(([label, s]) => {
                const v = s as typeof home;
                return <tr key={String(label)}><Td className="font-medium">{String(label)}</Td><Td className="text-right">{v.n}</Td><Td className="text-right">{num(v.ppg)}</Td><Td className="text-right">{num(v.gf)}</Td><Td className="text-right">{num(v.ga)}</Td><Td className="text-right">{num(v.xgf)}</Td><Td className="text-right">{num(v.xga)}</Td></tr>;
              })}
            </tbody>
          </Table>
        </Card>
        <Card title="Top players" subtitle="By xG this season">
          <Table>
            <thead><tr><Th>Player</Th><Th>Pos</Th><Th className="text-right">Min</Th><Th className="text-right">G</Th><Th className="text-right">xG</Th><Th className="text-right">xA</Th></tr></thead>
            <tbody>
              {players.map((p) => (
                <tr key={p.player_id}>
                  <Td><Link href={`/player/${p.player_id}`} className="hover:underline">{p.player}</Link></Td>
                  <Td className="text-fg-2" >{p.position_group ? <span title={POSITION_LABEL[p.position_group]}>{p.position_group}</span> : "–"}</Td>
                  <Td className="text-right">{p.minutes}</Td><Td className="text-right">{p.goals}</Td><Td className="text-right">{num(p.xg, 1)}</Td><Td className="text-right">{num(p.xa, 1)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>
      <Card title="Recent results">
        <Table>
          <thead><tr><Th>Date</Th><Th>Opponent</Th><Th>Venue</Th><Th className="text-right">Score</Th><Th className="text-right">xG</Th></tr></thead>
          <tbody>
            {[...matches].reverse().slice(0, 10).map((m) => (
              <tr key={m.match_id}>
                <Td className="text-fg-2">{dateOnly(m.kickoff_utc)}</Td>
                <Td><Link href={`/match/${m.match_id}`} className="hover:underline">{m.opponent}</Link></Td>
                <Td className="text-fg-2">{m.venue}</Td>
                <Td className="text-right font-medium">{m.outcome} {m.goals_for}–{m.goals_against}</Td>
                <Td className="text-right">{num(m.xg_for, 1)}–{num(m.xg_against, 1)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}

export default function TeamPage(props: PageProps<"/team/[id]">) {
  return <Suspense fallback={<div className="h-96 animate-pulse rounded-xl bg-surface-1" />}><TeamContent params={props.params} /></Suspense>;
}
