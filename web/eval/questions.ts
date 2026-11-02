/**
 * Ask agent evaluation set: 30 questions with reference SQL. The expected answer is the
 * result of the reference query on the live database, so the set stays valid as data
 * changes. Kept separate from the few-shot examples the agent sees (no leakage).
 */
export interface EvalCase { id: number; q: string; ref: string; key?: string }

export const CASES: EvalCase[] = [
  { id: 1, q: "Which Bundesliga forward has the best npxG per 90 this season, minimum 900 minutes?", ref: "select player from player_seasons where league_id='GER1' and season_id='2627' and position_group='FW' and minutes>=900 order by npxg_per90 desc limit 1" },
  { id: 2, q: "Who leads the Premier League in goals this season?", ref: "select player from player_seasons where league_id='ENG1' and season_id='2627' order by goals desc limit 1" },
  { id: 3, q: "Which La Liga team is top of the expected points table?", ref: "select team from league_table where league_id='ESP1' and season_id='2627' order by expected_points desc limit 1" },
  { id: 4, q: "Which Serie A team has the most points this season?", ref: "select team from league_table where league_id='ITA1' and season_id='2627' order by points desc limit 1" },
  { id: 5, q: "Which Ligue 1 team has underperformed its expected points the most?", ref: "select team from league_table where league_id='FRA1' and season_id='2627' order by points_minus_expected asc limit 1" },
  { id: 6, q: "How many goals have been scored in the Premier League this season?", ref: "select sum(home_goals + away_goals) from matches where league_id='ENG1' and season_id='2627' and status='finished'" },
  { id: 7, q: "How many penalties have been taken across all five leagues this season?", ref: "select count(*) from shots where season_id='2627' and situation='Penalty'" },
  { id: 8, q: "What share of shots this season were headers?", ref: "select round(avg((shot_type='Head')::int)::numeric, 3) from shots where season_id='2627' and result <> 'OwnGoal'" },
  { id: 9, q: "Which player has the most xA in Serie A this season?", ref: "select player from player_seasons where league_id='ITA1' and season_id='2627' order by xa desc limit 1" },
  { id: 10, q: "Which team has conceded the fewest goals in the Bundesliga this season?", ref: "select team from league_table where league_id='GER1' and season_id='2627' order by goals_against asc limit 1" },
  { id: 11, q: "Top 3 Premier League players by xGChain per 90 with at least 900 minutes", ref: "select player from player_seasons where league_id='ENG1' and season_id='2627' and minutes>=900 order by xg_chain_per90 desc limit 3" },
  { id: 12, q: "How many matches ended in a draw in La Liga this season?", ref: "select count(*) from matches where league_id='ESP1' and season_id='2627' and result='D'" },
  { id: 13, q: "What is the home win percentage across the five leagues this season?", ref: "select round(avg((result='H')::int)::numeric, 3) from matches where season_id='2627' and status='finished'" },
  { id: 14, q: "Which Ligue 1 player has scored the most goals above his xG this season?", ref: "select player from player_seasons where league_id='FRA1' and season_id='2627' order by goals_minus_xg desc limit 1" },
  { id: 15, q: "Which team generated the highest xG in a single match this season?", ref: "select team from team_matches where season_id='2627' order by xg_for desc limit 1" },
  { id: 16, q: "Average goals per match in Serie A this season", ref: "select round(avg(home_goals + away_goals)::numeric, 2) from matches where league_id='ITA1' and season_id='2627' and status='finished'" },
  { id: 17, q: "Which league has the highest average xG per shot this season, excluding penalties?", ref: "select league_id from shots where season_id='2627' and situation <> 'Penalty' and result <> 'OwnGoal' group by league_id order by avg(xg) desc limit 1" },
  { id: 18, q: "Which defender has the most xGBuildup per 90 in the Bundesliga this season (min 900 minutes)?", ref: "select player from player_seasons where league_id='GER1' and season_id='2627' and position_group='DEF' and minutes>=900 order by xg_buildup_per90 desc limit 1" },
  { id: 19, q: "How many shots did players take from outside the box in the Premier League this season?", ref: "select count(*) from shots where league_id='ENG1' and season_id='2627' and x_m < 88.5 and result <> 'OwnGoal'" },
  { id: 20, q: "Who scored the most goals in La Liga last season?", ref: "select player from player_seasons where league_id='ESP1' and season_id='2526' order by goals desc limit 1" },
  { id: 21, q: "Which Premier League team had the most expected points last season?", ref: "select team from league_table where league_id='ENG1' and season_id='2526' order by expected_points desc limit 1" },
  { id: 22, q: "In the backtest, which model has the lowest RPS overall?", ref: "select model from backtest_results where scope='all' order by rps asc limit 1" },
  { id: 23, q: "How many upcoming fixtures have an upset alert?", ref: "select count(*) from fixtures where upset_alert" },
  { id: 24, q: "Which upcoming match has the biggest edge between the model and the bookmakers?", ref: "select home_team, away_team from fixtures where max_edge is not null order by max_edge desc limit 1" },
  { id: 25, q: "What is the penalty conversion rate in the Premier League over all seasons in the database?", ref: "select round(avg(is_goal::int)::numeric, 3) from shots where league_id='ENG1' and situation='Penalty'" },
  { id: 26, q: "Which player under 21 has the most goals across the five leagues this season?", ref: "select player from player_seasons where season_id='2627' and age < 21 order by goals desc limit 1" },
  { id: 27, q: "Which Serie A team has the best goal difference this season?", ref: "select team from league_table where league_id='ITA1' and season_id='2627' order by goal_difference desc limit 1" },
  { id: 28, q: "How many different players have scored in the Bundesliga this season?", ref: "select count(*) from player_seasons where league_id='GER1' and season_id='2627' and goals > 0" },
  { id: 29, q: "Which team has the highest Elo rating right now?", ref: "select team from team_elo where valid_to >= current_date - 3 order by elo desc limit 1" },
  { id: 30, q: "Which Premier League team allowed the most xG per match this season?", ref: "select team from league_table where league_id='ENG1' and season_id='2627' and played > 0 order by xg_against / played desc limit 1" },
];

/** Normalise a result set to comparable tokens (numbers rounded, strings lower-cased). */
export function tokens(rows: Record<string, unknown>[]): string[] {
  return rows.flatMap((r) =>
    Object.values(r).map((v) => {
      const n = Number(v);
      return v !== null && v !== "" && !Number.isNaN(n) ? n.toFixed(2) : String(v).toLowerCase().trim();
    }),
  );
}

/** A case is correct if every value of the reference result appears in the agent's first rows. */
export function isCorrect(reference: Record<string, unknown>[], got: Record<string, unknown>[]): boolean {
  if (!reference.length) return got.length === 0;
  const have = new Set(tokens(got.slice(0, Math.max(reference.length, 10))));
  return tokens(reference).every((t) => have.has(t));
}
