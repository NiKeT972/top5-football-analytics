import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ScoutResults } from "@/components/scout-results";
import { Card, EmptyState, PageHeader } from "@/components/ui/card";
import { METRIC_LABEL, SITE } from "@/lib/config";
import { getPercentiles, getPlayerSeasons, scout, searchPlayers } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { LEAGUES, leagueById } from "@/lib/leagues";

export const metadata: Metadata = {
  title: "Scout: find similar players",
  description: "Find players with a similar per-90 profile, filtered by league, age and minutes, with radar overlays.",
};

type SP = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

async function ScoutContent({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const q = one(sp.q) ?? "";
  const playerId = Number(one(sp.player));
  const league = one(sp.league) || undefined;
  const maxAge = one(sp.max_age) ? Number(one(sp.max_age)) : undefined;
  const minMinutes = Number(one(sp.min_minutes) ?? SITE.scoutDefaultMinMinutes);

  const seasons = Number.isFinite(playerId) && playerId > 0 ? await getPlayerSeasons(playerId) : [];
  const season = one(sp.season) ?? seasons[0]?.season_id;
  const picked = seasons.find((s) => s.season_id === season) ?? seasons[0];
  // A typed name that differs from the picked player starts a new search.
  const searching = Boolean(q) && (!picked || q.toLowerCase() !== picked.player.toLowerCase());
  const target = searching ? undefined : picked;
  const matches = searching ? await searchPlayers(q) : [];

  const results = target ? await scout({ playerId: target.player_id, seasonId: target.season_id, leagueId: league, maxAge, minMinutes }) : [];
  const pctRows = target ? await getPercentiles([target.player_id, ...results.map((r) => r.player_id)], target.season_id) : [];
  const pct: Record<number, Record<string, number>> = {};
  for (const r of pctRows) (pct[r.player_id] ??= {})[METRIC_LABEL[r.metric] ?? r.metric] = r.percentile;

  return (
    <div className="space-y-6">
      <Card>
        <form className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto] sm:items-end" action="/scout">
          {target && <input type="hidden" name="player" value={target.player_id} />}
          {target && <input type="hidden" name="season" value={target.season_id} />}
          {/* Typing a different name ignores the hidden player and searches again. */}
          <label className="text-sm text-fg-2">Player
            <input name="q" defaultValue={q || target?.player || ""} placeholder="e.g. Saka" className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-fg" />
          </label>
          <label className="text-sm text-fg-2">League
            <select name="league" defaultValue={league ?? ""} className="mt-1 w-full rounded-md border border-border bg-surface-1 px-2 py-2 text-fg">
              <option value="">All five</option>
              {LEAGUES.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          <label className="text-sm text-fg-2">Max age
            <select name="max_age" defaultValue={maxAge ? String(maxAge) : ""} className="mt-1 w-full rounded-md border border-border bg-surface-1 px-2 py-2 text-fg">
              <option value="">Any</option>
              {SITE.scoutMaxAgeOptions.map((a) => <option key={a} value={a}>≤ {a}</option>)}
            </select>
          </label>
          <label className="text-sm text-fg-2">Min minutes
            <input name="min_minutes" type="number" min={0} step={90} defaultValue={minMinutes} className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-fg" />
          </label>
          <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">Search</button>
        </form>
      </Card>

      {searching && (
        <Card title="Pick a player">
          {matches.length === 0 ? <p className="text-sm text-fg-3">No players match “{q}”.</p> : (
            <ul className="divide-y divide-border">
              {matches.map((m) => (
                <li key={`${m.player_id}-${m.season_id}-${m.league_id}`}>
                  <Link href={`/scout?player=${m.player_id}&season=${m.season_id}`} className="flex justify-between py-2 hover:text-accent">
                    <span className="font-medium">{m.player}</span>
                    <span className="text-sm text-fg-3">{m.team ?? m.team_names} · {leagueById(m.league_id)?.name} · {seasonLabel(m.season_id)} · {m.minutes} min</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {target && (
        <Card title={`Players like ${target.player}`} subtitle={`${seasonLabel(target.season_id)} · ${target.position_group ?? ""} · filters: ${league ? leagueById(league)?.name : "all leagues"}, ${maxAge ? `age ≤ ${maxAge}` : "any age"}, ≥ ${minMinutes} min`}>
          {results.length ? (
            <ScoutResults target={{ id: target.player_id, name: target.player }} results={results.map((r) => ({ ...r, league: leagueById(r.league_id)?.short ?? r.league_id }))} metrics={SITE.radarMetrics.map((m) => METRIC_LABEL[m] ?? m)} pct={pct} />
          ) : <p className="text-sm text-fg-3">No matches. Players need at least {SITE.scoutDefaultMinMinutes} minutes to be profiled, and goalkeepers are excluded.</p>}
        </Card>
      )}

      {!q && !target && (
        <EmptyState title="Search for a player to start">
          Similarity uses standardised per-90 attacking and build-up metrics (npxG, xA, shots, key passes, xGChain, xGBuildup…), compared only within the same position group and season.
        </EmptyState>
      )}
    </div>
  );
}

export default function ScoutPage(props: PageProps<"/scout">) {
  return (
    <>
      <PageHeader title="Scout" subtitle="Find players like X, filtered by league, age and minutes." />
      <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-surface-1" />}>
        <ScoutContent searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}
