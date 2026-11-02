import Link from "next/link";
import { FixtureRow } from "@/components/fixture-row";
import { Badge, Card, EmptyState, PageHeader } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { SITE } from "@/lib/config";
import { cacheLife, cacheTag } from "next/cache";
import { DATA_TAG, type Fixture, getFixtures } from "@/lib/data";
import { kickoff, pct, signed, TZ } from "@/lib/format";
import { LEAGUES } from "@/lib/leagues";

const OUTCOME = { H: "home win", D: "draw", A: "away win" } as const;

function dayKey(iso: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));
}

function edgeOf(f: Fixture) {
  const o = f.edge_outcome;
  if (!o || f.max_edge == null) return null;
  const model = o === "H" ? f.p_home : o === "D" ? f.p_draw : f.p_away;
  const book = o === "H" ? f.book_p_home : o === "D" ? f.book_p_draw : f.book_p_away;
  return { o, model, book, edge: f.max_edge };
}

export default async function Home() {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const fixtures = await getFixtures(SITE.fixtureDays);
  const today = dayKey(new Date().toISOString());
  const todays = fixtures.filter((f) => dayKey(f.kickoff_utc) === today);
  const upsets = fixtures.filter((f) => f.upset_alert);
  const edges = fixtures
    .filter((f) => (f.max_edge ?? 0) >= SITE.edgeMin)
    .sort((a, b) => (b.max_edge ?? 0) - (a.max_edge ?? 0))
    .slice(0, SITE.maxEdges);

  return (
    <>
      <PageHeader
        title="This week across Europe's top 5 leagues"
        subtitle="Win/draw/loss probabilities and the most likely scoreline for every fixture, from a Dixon–Coles + LightGBM ensemble retrained weekly."
      />
      {fixtures.length === 0 ? (
        <EmptyState title="No upcoming fixtures with data yet">
          Either it is an international break or the daily data pipeline has not published yet. See the{" "}
          <Link className="underline" href="/model">model page</Link> for the track record.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-6">
            {todays.length > 0 && (
              <Card title="Today" subtitle={`${todays.length} matches`}>
                <div className="-mx-3">{todays.map((f) => <FixtureRow key={f.match_id} f={f} />)}</div>
              </Card>
            )}
            {LEAGUES.map((l) => {
              const lf = fixtures.filter((f) => f.league_id === l.id && dayKey(f.kickoff_utc) !== today);
              if (!lf.length) return null;
              return (
                <Card key={l.id} title={<Link href={`/league/${l.slug}`} className="hover:underline">{l.name}</Link>} subtitle="Next 7 days">
                  <div className="-mx-3">{lf.map((f) => <FixtureRow key={f.match_id} f={f} />)}</div>
                </Card>
              );
            })}
          </div>
          <aside className="min-w-0 space-y-6">
            <Card title="Upset alerts" subtitle="Bookmaker underdog that the model rates much higher">
              {upsets.length === 0 ? <p className="text-sm text-fg-3">None this week.</p> : (
                <ul className="space-y-3">
                  {upsets.map((f) => {
                    const homeDog = (f.book_p_home ?? 0) < (f.book_p_away ?? 0);
                    const team = homeDog ? f.home_team : f.away_team;
                    return (
                      <li key={f.match_id}>
                        <Link href={`/match/${f.match_id}`} className="block rounded-lg bg-surface-2 p-3 hover:ring-1 hover:ring-border">
                          <div className="text-sm font-medium text-fg">{team} to win</div>
                          <div className="text-xs text-fg-2">
                            Model {pct(homeDog ? f.p_home : f.p_away)} vs bookmakers {pct(homeDog ? f.book_p_home : f.book_p_away)}
                          </div>
                          <div className="text-xs text-fg-3">{f.home_team} v {f.away_team} · {kickoff(f.kickoff_utc)}</div>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
            <Card title="Biggest edges vs bookmakers" subtitle="Model probability minus margin-free market probability">
              {edges.length === 0 ? <p className="text-sm text-fg-3">No pre-match odds published yet for this week.</p> : (
                <Table>
                  <thead><tr><Th>Match</Th><Th>Pick</Th><Th className="text-right">Edge</Th></tr></thead>
                  <tbody>
                    {edges.map((f) => {
                      const e = edgeOf(f)!;
                      return (
                        <tr key={f.match_id}>
                          <Td><Link href={`/match/${f.match_id}`} className="hover:underline">{f.home_team} v {f.away_team}</Link></Td>
                          <Td><span className="text-fg-2">{OUTCOME[e.o]}</span></Td>
                          <Td className="text-right"><Badge tone="accent">{signed(e.edge * 100, 1)} pp</Badge></Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              )}
              <p className="mt-3 text-xs text-fg-3">An edge is a disagreement, not a recommendation. Bookmakers usually win: see the <Link href="/model" className="underline">track record</Link>.</p>
            </Card>
          </aside>
        </div>
      )}
    </>
  );
}
