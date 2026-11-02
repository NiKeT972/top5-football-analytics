/** Static league metadata (URL slug <-> canonical league_id). */
export interface LeagueMeta {
  id: string;
  slug: string;
  name: string;
  country: string;
  short: string;
}

export const LEAGUES: LeagueMeta[] = [
  { id: "ENG1", slug: "premier-league", name: "Premier League", country: "England", short: "EPL" },
  { id: "ESP1", slug: "la-liga", name: "La Liga", country: "Spain", short: "LAL" },
  { id: "GER1", slug: "bundesliga", name: "Bundesliga", country: "Germany", short: "BUN" },
  { id: "ITA1", slug: "serie-a", name: "Serie A", country: "Italy", short: "SEA" },
  { id: "FRA1", slug: "ligue-1", name: "Ligue 1", country: "France", short: "L1" },
];

export const leagueBySlug = (slug: string) => LEAGUES.find((l) => l.slug === slug);
export const leagueById = (id: string) => LEAGUES.find((l) => l.id === id);
