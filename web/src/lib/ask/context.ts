/**
 * Retrieval context for the Ask agent: the schema of the read-only views, football
 * definitions, and worked examples. Examples are retrieved per question by lexical
 * similarity (at this size, a few dozen short documents, lexical retrieval beats an
 * embedding round-trip on latency and cost, and keeps the agent free to run).
 */

export const SCHEMA_DOC = `
Postgres views (read-only). Seasons: season_id '2627' = 2026/27 (current), '2526' = 2025/26, '2425' = 2024/25.
League ids: ENG1 Premier League, ESP1 La Liga, GER1 Bundesliga, ITA1 Serie A, FRA1 Ligue 1.

leagues(league_id, name, country, n_teams)
teams(team_id, name, league_id, league_name, country)
matches(match_id, league_id, league_name, season_id, season_label, kickoff_utc, status['scheduled'|'finished'|'pending'],
  home_team_id, home_team, away_team_id, away_team, home_goals, away_goals, result['H'|'D'|'A'],
  home_xg, away_xg  -- PitchIQ xG
  , home_xg_understat, away_xg_understat)
team_matches(match_id, league_id, season_id, kickoff_utc, team_id, team, opponent_id, opponent, venue['home'|'away'],
  goals_for, goals_against, xg_for, xg_against, outcome['W'|'D'|'L'], points)  -- finished matches, one row per team
league_table(league_id, season_id, season_label, team_id, team, position, played, won, drawn, lost, goals_for, goals_against,
  goal_difference, points, xg_for, xg_against, expected_points, expected_points_position, points_minus_expected)
team_elo(team_id, team, valid_from, valid_to, elo)
shots(shot_id, match_id, league_id, season_id, kickoff_utc, team_id, team, side, player_id, player, minute, x_m, y_m,
  distance_m, angle_rad, situation['OpenPlay'|'FromCorner'|'SetPiece'|'DirectFreekick'|'Penalty'],
  shot_type['RightFoot'|'LeftFoot'|'Head'|'OtherBodyParts'], last_action,
  result['Goal'|'SavedShot'|'MissedShots'|'BlockedShot'|'ShotOnPost'|'OwnGoal'], is_goal, xg, xg_understat)
player_seasons(player_id, player, season_id, season_label, league_id, team_id, team, team_names, position_group['FW'|'AMW'|'CM'|'DEF'|'GK'],
  age, nation, games, minutes, goals, np_goals, assists, shots, key_passes, xg, npxg, xa, xg_chain, xg_buildup,
  yellow_cards, red_cards, npxg_per90, xg_per90, xa_per90, goals_per90, np_goals_per90, assists_per90, shots_per90,
  key_passes_per90, xg_chain_per90, xg_buildup_per90, goals_minus_xg)  -- one row per player, season and league
player_matches(match_id, kickoff_utc, league_id, season_id, player_id, player, team_id, team, position, minutes, goals,
  own_goals, assists, shots, key_passes, xg, xa, xg_chain, xg_buildup, yellow_cards, red_cards)
player_percentiles(player_id, player, season_id, league_id, position_group, metric, per90, percentile)
similar_players(player_id, player, season_id, league_id, rank, other_player_id, other_player, other_league_id, similarity)
fixtures(match_id, league_id, league_name, kickoff_utc, home_team, away_team, p_home, p_draw, p_away, exp_home_goals,
  exp_away_goals, top_score, book_p_home, book_p_draw, book_p_away, max_edge, edge_outcome, upset_alert)  -- upcoming only
prediction_track_record(match_id, league_id, season_id, kickoff_utc, home_team, away_team, result, model, p_home, p_draw,
  p_away, log_loss, brier, rps, book_log_loss, book_brier, book_rps)
backtest_results(scope, league_id, season_id, model, matches, log_loss, brier, rps)
`.trim();

export const GLOSSARY = `
Definitions: xG = expected goals (probability a shot scores). npxG = non-penalty xG. xA = expected assists.
xGChain = xG of every possession a player was involved in; xGBuildup = the same excluding shots and key passes.
"per 90" = per 90 minutes played; prefer the *_per90 columns. "This season" = season_id '2627'; "last season" = '2526'.
"Forward" = position_group 'FW'; "winger"/"attacking midfielder" = 'AMW'; "midfielder" = 'CM' (or 'AMW' if attacking);
"defender" = 'DEF'; "goalkeeper" = 'GK'. Over-performance = goals minus xG (players) or points_minus_expected (teams).
Apply minimum-minutes filters when the user gives one; otherwise use minutes >= 450 for per-90 rankings.
Expected points (xPts) = expected_points in league_table.
`.trim();

export interface Example { q: string; sql: string }

export const EXAMPLES: Example[] = [
  { q: "Which La Liga winger has the best xA per 90 this season, minimum 600 minutes?", sql: "select player, team, minutes, xa_per90 from player_seasons where league_id = 'ESP1' and season_id = '2627' and position_group = 'AMW' and minutes >= 600 order by xa_per90 desc limit 10" },
  { q: "Top 5 Premier League teams by expected points this season", sql: "select team, points, round(expected_points::numeric, 1) as xpts from league_table where league_id = 'ENG1' and season_id = '2627' order by expected_points desc limit 5" },
  { q: "Which team has overperformed its xPts the most in La Liga?", sql: "select team, points, round(expected_points::numeric, 1) as xpts, round(points_minus_expected::numeric, 1) as diff from league_table where league_id = 'ESP1' and season_id = '2627' order by points_minus_expected desc limit 5" },
  { q: "Who has scored the most goals above xG in Serie A this season?", sql: "select player, team, goals, round(xg::numeric, 1) as xg, goals_minus_xg from player_seasons where league_id = 'ITA1' and season_id = '2627' order by goals_minus_xg desc limit 10" },
  { q: "How many headed goals have been scored in each league this season?", sql: "select league_id, count(*) as headed_goals from shots where season_id = '2627' and shot_type = 'Head' and is_goal group by league_id order by headed_goals desc" },
  { q: "Average xG per shot from outside the box by league", sql: "select league_id, round(avg(xg)::numeric, 3) as avg_xg, count(*) as shots from shots where season_id = '2627' and distance_m > 18 and situation <> 'Penalty' group by league_id order by avg_xg desc" },
  { q: "Show Arsenal's last 10 results with xG", sql: "select kickoff_utc::date as date, opponent, venue, goals_for, goals_against, round(xg_for::numeric, 2) as xg_for, round(xg_against::numeric, 2) as xg_against from team_matches where team = 'Arsenal' order by kickoff_utc desc limit 10" },
  { q: "Which upcoming matches have upset alerts?", sql: "select kickoff_utc, home_team, away_team, round(p_home::numeric, 2) as p_home, round(book_p_home::numeric, 2) as book_home, round(p_away::numeric, 2) as p_away, round(book_p_away::numeric, 2) as book_away from fixtures where upset_alert order by kickoff_utc" },
  { q: "How does the model compare to bookmakers in the backtest?", sql: "select model, matches, round(log_loss::numeric, 4) as log_loss, round(rps::numeric, 4) as rps from backtest_results where scope = 'all' order by rps" },
  { q: "Penalty conversion rate by league", sql: "select league_id, count(*) as penalties, round(avg(is_goal::int)::numeric, 3) as conversion from shots where situation = 'Penalty' group by league_id order by conversion desc" },
  { q: "Most key passes per 90 among Ligue 1 midfielders under 23", sql: "select player, team, age, minutes, key_passes_per90 from player_seasons where league_id = 'FRA1' and season_id = '2627' and position_group in ('CM', 'AMW') and age < 23 and minutes >= 450 order by key_passes_per90 desc limit 10" },
  { q: "Players most similar to Bukayo Saka", sql: "select other_player, other_league_id, round(similarity::numeric, 3) as similarity from similar_players where player ilike '%Saka%' and season_id = '2627' order by rank limit 10" },
  { q: "Elo rating trend of Real Madrid this season", sql: "select valid_from, round(elo::numeric) as elo from team_elo where team = 'Real Madrid' and valid_to >= '2026-07-01' order by valid_from" },
  { q: "Which teams concede the most xG per match in the Premier League?", sql: "select team, played, round((xg_against / played)::numeric, 2) as xga_per_match from league_table where league_id = 'ENG1' and season_id = '2627' order by xga_per_match desc limit 10" },
];

const STOP = new Set("the a an of in by for to with is are has have which who what how most this season per show me than and or".split(" "));
const tokens = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((t) => t && !STOP.has(t));

/** Top-k examples by token overlap (Jaccard) with the question. */
export function retrieveExamples(question: string, k = 4): Example[] {
  const q = new Set(tokens(question));
  return [...EXAMPLES]
    .map((e) => {
      const t = new Set(tokens(e.q));
      const inter = [...q].filter((x) => t.has(x)).length;
      return { e, score: inter / (q.size + t.size - inter || 1) };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((x) => x.e);
}
