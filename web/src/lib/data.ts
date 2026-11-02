/**
 * Data access layer. Every reader is a cached function tagged `pitchiq-data`, so pages are
 * served from the cache and the daily pipeline refreshes everything with one
 * `revalidateTag('pitchiq-data')` call (see app/api/revalidate).
 *
 * Readers never throw: if the database is not configured or a query fails, they log and
 * return an empty result so pages can render an honest empty state.
 */
import { cacheLife, cacheTag } from "next/cache";
import { db, isConfigured } from "./supabase";

export const DATA_TAG = "pitchiq-data";

type Row = Record<string, unknown>;

/** PostgREST filter builder (kept loose: each reader chains different filters). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Query = any;

async function select<T = Row>(view: string, build: (q: Query) => Query, columns = "*"): Promise<T[]> {
  if (!isConfigured()) return [];
  try {
    const { data, error } = (await build(db().from(view).select(columns))) as {
      data: T[] | null;
      error: { message: string } | null;
    };
    if (error) {
      console.error(`[data] ${view}: ${error.message}`);
      return [];
    }
    return data ?? [];
  } catch (e) {
    console.error(`[data] ${view}:`, e);
    return [];
  }
}

async function rpc<T = Row>(fn: string, args: Record<string, unknown>): Promise<T[]> {
  if (!isConfigured()) return [];
  const { data, error } = await db().rpc(fn, args, { get: true });
  if (error) {
    console.error(`[data] rpc ${fn}: ${error.message}`);
    return [];
  }
  return (data as T[]) ?? [];
}

// ------------------------------------------------------------------ types
export interface Freshness {
  generated_utc: string;
  generated_display: string;
  last_success_utc: string | null;
  season: string;
  leagues: Record<string, { name: string; latest_finished_match_utc: string | null; finished_matches_current_season: number }>;
  sources: Record<string, { ok: boolean; message: string }>;
}

export interface Fixture {
  match_id: number; league_id: string; league_name: string; kickoff_utc: string;
  home_team_id: string; home_team: string; away_team_id: string; away_team: string;
  p_home: number | null; p_draw: number | null; p_away: number | null;
  exp_home_goals: number | null; exp_away_goals: number | null; top_score: string | null;
  book_p_home: number | null; book_p_draw: number | null; book_p_away: number | null;
  odds_h: number | null; odds_d: number | null; odds_a: number | null;
  max_edge: number | null; edge_outcome: "H" | "D" | "A" | null; upset_alert: boolean;
}

export interface Match {
  match_id: number; league_id: string; league_name: string; season_id: string; season_label: string;
  kickoff_utc: string; status: string; home_team_id: string; home_team: string; away_team_id: string;
  away_team: string; home_goals: number | null; away_goals: number | null; result: "H" | "D" | "A" | null;
  home_xg: number | null; away_xg: number | null; home_xg_understat: number | null; away_xg_understat: number | null;
}

export interface Shot {
  shot_id: number; match_id: number; team_id: string; team: string; side: "h" | "a"; player_id: number;
  player: string | null; minute: number; x_m: number; y_m: number; situation: string; shot_type: string;
  last_action: string | null; result: string; is_goal: boolean; xg: number | null; xg_understat: number | null;
}

export interface TableRow {
  league_id: string; season_id: string; team_id: string; team: string; position: number; played: number;
  won: number; drawn: number; lost: number; goals_for: number; goals_against: number; goal_difference: number;
  points: number; xg_for: number; xg_against: number; expected_points: number; expected_points_position: number;
  points_minus_expected: number;
}

export interface PlayerSeason {
  player_id: number; player: string; season_id: string; season_label: string; league_id: string; team_id: string | null;
  team: string | null; team_names: string | null; position_group: string | null; age: number | null; nation: string | null; games: number;
  minutes: number; goals: number; np_goals: number; assists: number; shots: number; key_passes: number; xg: number;
  npxg: number; xa: number; xg_chain: number; xg_buildup: number; npxg_per90: number; xa_per90: number;
  goals_per90: number; shots_per90: number; key_passes_per90: number; xg_chain_per90: number;
  xg_buildup_per90: number; goals_minus_xg: number;
}

export interface Percentile { player_id: number; season_id: string; metric: string; per90: number; percentile: number }

export interface TrackRow {
  match_id: number; league_id: string; season_id: string; kickoff_utc: string; home_team: string; away_team: string;
  result: string; model: string; p_home: number; p_draw: number; p_away: number; log_loss: number; brier: number;
  rps: number; book_log_loss: number | null; book_brier: number | null; book_rps: number | null;
}

// ------------------------------------------------------------------ readers

export async function getFreshness(): Promise<Freshness | null> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const rows = await select<{ doc: Freshness }>("freshness", (q) => q.limit(1));
  return rows[0]?.doc ?? null;
}

export async function getFixtures(days: number): Promise<Fixture[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const until = new Date(Date.now() + days * 86_400_000).toISOString();
  return select<Fixture>("fixtures", (q) => q.lte("kickoff_utc", until).order("kickoff_utc"));
}

export async function getRecentResults(limit: number): Promise<Match[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<Match>("matches", (q) => q.eq("status", "finished").order("kickoff_utc", { ascending: false }).limit(limit));
}

export async function getSeasons(leagueId: string): Promise<string[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const rows = await select<{ season_id: string }>("league_table", (q) => q.eq("league_id", leagueId), "season_id");
  return [...new Set(rows.map((r) => r.season_id))].sort().reverse();
}

export async function getLeagueTable(leagueId: string, seasonId: string): Promise<TableRow[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<TableRow>("league_table", (q) => q.eq("league_id", leagueId).eq("season_id", seasonId).order("position"));
}

export async function getEloHistory(teamIds: string[], fromDate: string) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  if (!teamIds.length) return [];
  return select<{ team_id: string; team: string; valid_from: string; valid_to: string; elo: number }>("team_elo", (q) =>
    q.in("team_id", teamIds).gte("valid_to", fromDate).order("valid_from"),
  );
}

export async function getMatch(id: number): Promise<Match | null> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const rows = await select<Match>("matches", (q) => q.eq("match_id", id).limit(1));
  return rows[0] ?? null;
}

export async function getMatchShots(id: number): Promise<Shot[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<Shot>("shots", (q) => q.eq("match_id", id).order("minute"));
}

export async function getMatchPrediction(id: number) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ model: string; created_utc: string; p_home: number; p_draw: number; p_away: number; exp_home_goals: number; exp_away_goals: number; top_score: string; score_grid: number[][] | null }>(
    "latest_predictions",
    (q) => q.eq("match_id", id),
  );
}

export async function getMatchPlayers(id: number) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ player_id: number; player: string; team_id: string; minutes: number; goals: number; assists: number; shots: number; key_passes: number; xg: number; xa: number }>(
    "player_matches",
    (q) => q.eq("match_id", id).order("xg", { ascending: false }),
  );
}

export async function getTeam(teamId: string) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const rows = await select<{ team_id: string; name: string; league_id: string; league_name: string; country: string }>("teams", (q) =>
    q.eq("team_id", teamId).limit(1),
  );
  return rows[0] ?? null;
}

export async function getTeamMatches(teamId: string) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ match_id: number; season_id: string; kickoff_utc: string; opponent: string; opponent_id: string; venue: string; goals_for: number; goals_against: number; xg_for: number | null; xg_against: number | null; outcome: string; points: number }>(
    "team_matches",
    (q) => q.eq("team_id", teamId).order("kickoff_utc"),
  );
}

export async function getTeamPlayers(teamId: string, seasonId: string): Promise<PlayerSeason[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<PlayerSeason>("player_seasons", (q) => q.eq("team_id", teamId).eq("season_id", seasonId).order("xg", { ascending: false }).limit(12));
}

export async function getPlayerSeasons(playerId: number): Promise<PlayerSeason[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<PlayerSeason>("player_seasons", (q) => q.eq("player_id", playerId).order("season_id", { ascending: false }));
}

export async function getPercentiles(playerIds: number[], seasonId: string): Promise<Percentile[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  if (!playerIds.length) return [];
  return select<Percentile>("player_percentiles", (q) => q.in("player_id", playerIds).eq("season_id", seasonId));
}

export async function getSimilar(playerId: number, seasonId: string) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ rank: number; other_player_id: number; other_player: string; other_league_id: string; similarity: number }>(
    "similar_players",
    (q) => q.eq("player_id", playerId).eq("season_id", seasonId).order("rank"),
  );
}

export async function getPlayerMatches(playerId: number) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ match_id: number; kickoff_utc: string; season_id: string; minutes: number; goals: number; xg: number }>(
    "player_matches",
    (q) => q.eq("player_id", playerId).order("kickoff_utc"),
  );
}

export async function searchPlayers(query: string, seasonId?: string): Promise<PlayerSeason[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const q = query.trim();
  if (q.length < 2) return [];
  return select<PlayerSeason>("player_seasons", (b) => {
    let x = b.ilike("player", `%${q.replace(/[%_]/g, "")}%`);
    if (seasonId) x = x.eq("season_id", seasonId);
    return x.order("minutes", { ascending: false }).limit(12);
  });
}

export async function scout(args: { playerId: number; seasonId: string; leagueId?: string; maxAge?: number; minMinutes: number }) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return rpc<{ player_id: number; player: string; team: string; league_id: string; position_group: string; age: number | null; minutes: number; similarity: number }>(
    "scout_similar",
    { p_player_id: args.playerId, p_season_id: args.seasonId, p_league_id: args.leagueId ?? null, p_max_age: args.maxAge ?? null, p_min_minutes: args.minMinutes, p_limit: 20 },
  );
}

export async function getTrackRecord(): Promise<TrackRow[]> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<TrackRow>("prediction_track_record", (q) => q.order("kickoff_utc", { ascending: false }).limit(5000));
}

export async function getBacktest() {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ scope: string; league_id: string; season_id: string; model: string; matches: number; log_loss: number; brier: number; rps: number }>("backtest_results", (q) => q);
}

export async function getCalibration(family: string) {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  return select<{ model: string; outcome: string; bin: number; mean_pred: number; obs_freq: number; n: number }>("calibration", (q) =>
    q.eq("family", family).order("bin"),
  );
}

export async function getModelMeta(name: string): Promise<Record<string, unknown> | null> {
  "use cache";
  cacheTag(DATA_TAG);
  cacheLife("hours");
  const rows = await select<{ meta: Record<string, unknown> }>("model_meta", (q) => q.eq("name", name).limit(1));
  return rows[0]?.meta ?? null;
}

