import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { EloChart, XgScatter } from "@/components/charts/client";
import { Card, EmptyState, PageHeader } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { getEloHistory, getLeagueTable, getSeasons, type TableRow } from "@/lib/data";
import { num, seasonLabel, signed } from "@/lib/format";
import { LEAGUES, leagueBySlug } from "@/lib/leagues";

export async function generateStaticParams() {
  return LEAGUES.map((l) => ({ slug: l.slug, season: [] }));
}

export async function generateMetadata({ params }: PageProps<"/league/[slug]/[[...season]]">): Promise<Metadata> {
  const { slug } = await params;
  const l = leagueBySlug(slug);
  return l ? { title: `${l.name} table, xPts and Elo`, description: `${l.name} league table next to the expected-points table, over/under-performance, Elo ratings and xG for vs against.` } : {};
}

function PerfCell({ v }: { v: number }) {
  const tone = v >= 0 ? "var(--div-pos)" : "var(--div-neg)";
  return <span className="tabular font-medium" style={{ color: tone }}>{signed(v, 1)}</span>;
}

function Tables({ rows }: { rows: TableRow[] }) {
  const byXpts = [...rows].sort((a, b) => a.expected_points_position - b.expected_points_position);
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card title="League table" subtitle="Actual results, with each team's points minus expected points">
        <Table>
          <thead><tr><Th>#</Th><Th>Team</Th><Th className="text-right">P</Th><Th className="text-right">W-D-L</Th><Th className="text-right">GD</Th><Th className="text-right">Pts</Th><Th className="text-right" title="Points minus expected points">+/− xPts</Th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.team_id}>
                <Td className="text-fg-3">{r.position}</Td>
                <Td><Link href={`/team/${r.team_id}`} className="font-medium hover:underline">{r.team}</Link></Td>
                <Td className="text-right">{r.played}</Td>
                <Td className="text-right text-fg-2">{r.won}-{r.drawn}-{r.lost}</Td>
                <Td className="text-right">{signed(r.goal_difference, 0)}</Td>
                <Td className="text-right font-semibold">{r.points}</Td>
                <Td className="text-right"><PerfCell v={r.points_minus_expected} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card title="Expected-points table" subtitle="Ranked by xPts: 10,000 shot-by-shot simulations of every match">
        <Table>
          <thead><tr><Th>#</Th><Th>Team</Th><Th className="text-right">xG</Th><Th className="text-right">xGA</Th><Th className="text-right">xPts</Th><Th className="text-right">Actual #</Th></tr></thead>
          <tbody>
            {byXpts.map((r) => (
              <tr key={r.team_id}>
                <Td className="text-fg-3">{r.expected_points_position}</Td>
                <Td><Link href={`/team/${r.team_id}`} className="font-medium hover:underline">{r.team}</Link></Td>
                <Td className="text-right">{num(r.xg_for, 1)}</Td>
                <Td className="text-right">{num(r.xg_against, 1)}</Td>
                <Td className="text-right font-semibold">{num(r.expected_points, 1)}</Td>
                <Td className="text-right text-fg-2">{r.position}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}

async function LeagueContent({ params }: { params: PageProps<"/league/[slug]/[[...season]]">["params"] }) {
  const { slug, season } = await params;
  const league = leagueBySlug(slug);
  if (!league) notFound();
  const seasons = await getSeasons(league.id);
  const seasonId = season?.[0] ?? seasons[0];
  if (!seasonId) {
    return <EmptyState title="No data published for this league yet" />;
  }
  const rows = await getLeagueTable(league.id, seasonId);
  const from = `20${seasonId.slice(0, 2)}-07-01`;
  const elo = await getEloHistory(rows.map((r) => r.team_id), from);
  const series = rows.map((r) => ({
    team_id: r.team_id,
    team: r.team,
    points: elo.filter((e) => e.team_id === r.team_id).map((e) => ({ t: Math.max(new Date(e.valid_from).getTime(), new Date(from).getTime()), elo: e.elo })),
  }));
  const scatter = rows.filter((r) => r.played > 0).map((r) => ({ team: r.team, xgFor: r.xg_for / r.played, xgAgainst: r.xg_against / r.played }));
  return (
    <>
      <PageHeader title={league.name} subtitle={`${seasonLabel(seasonId)} season · ${league.country}`}>
        <nav className="flex flex-wrap gap-1 text-sm">
          {seasons.map((s) => (
            <Link key={s} href={`/league/${slug}/${s}`} className={`rounded-md px-2.5 py-1 ${s === seasonId ? "bg-accent text-white" : "bg-surface-2 text-fg-2 hover:text-fg"}`}>{seasonLabel(s)}</Link>
          ))}
        </nav>
      </PageHeader>
      {rows.length === 0 ? <EmptyState title="Table not available yet" /> : (
        <div className="space-y-6">
          <Tables rows={rows} />
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Elo ratings this season" subtitle="Strength over time, highlight any club">
              {elo.length ? <EloChart series={series} /> : <p className="text-sm text-fg-3">Elo ratings unavailable (ClubElo has not been reachable).</p>}
            </Card>
            <Card title="Chance creation vs chance prevention" subtitle="xG for and against per match; top-right is best">
              <XgScatter points={scatter} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

export default function LeaguePage(props: PageProps<"/league/[slug]/[[...season]]">) {
  return (
    <Suspense fallback={<div className="h-96 animate-pulse rounded-xl bg-surface-1" />}>
      <LeagueContent params={props.params} />
    </Suspense>
  );
}
