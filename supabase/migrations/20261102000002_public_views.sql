-- Read-only, documented views for the website and the Ask agent.
-- Column comments double as the Ask agent's schema documentation.

create table core.site_settings (key text primary key, value real not null, description text not null);
insert into core.site_settings values
  ('upset_min_model_prob', 0.30, 'Upset alert: model win probability for the bookmaker underdog must be at least this'),
  ('upset_min_edge', 0.05, 'Upset alert: and exceed the bookmaker probability by at least this'),
  ('edge_min', 0.04, 'Biggest edges list: minimum model minus bookmaker probability');

create or replace function public.season_label(season_id text) returns text
language sql immutable set search_path = '' as $$ select (2000 + left(season_id, 2)::int)::text || '/' || right(season_id, 2) $$;

-- ------------------------------------------------------------------ reference
create view public.leagues as
select league_id, name, country, n_teams from core.leagues;
comment on view public.leagues is 'The five leagues. league_id: ENG1 Premier League, ESP1 La Liga, GER1 Bundesliga, ITA1 Serie A, FRA1 Ligue 1.';

create view public.teams as
select t.team_id, t.name, t.league_id, l.name as league_name, t.country
from core.teams t join core.leagues l using (league_id);
comment on view public.teams is 'Clubs with a canonical team_id slug, e.g. eng-arsenal. league_id is the club''s most recent league.';

-- ------------------------------------------------------------------ matches
create view public.matches as
select m.match_id, m.league_id, l.name as league_name, m.season_id, public.season_label(m.season_id) as season_label,
       m.kickoff_utc, m.status,
       m.home_team_id, ht.name as home_team, m.away_team_id, aw.name as away_team,
       m.home_goals, m.away_goals,
       case when m.status = 'finished' then
         case when m.home_goals > m.away_goals then 'H' when m.home_goals = m.away_goals then 'D' else 'A' end
       end as result,
       m.home_xg, m.away_xg, m.home_xg_understat, m.away_xg_understat
from core.matches m
join core.leagues l using (league_id)
join core.teams ht on ht.team_id = m.home_team_id
join core.teams aw on aw.team_id = m.away_team_id;
comment on view public.matches is 'One row per league match. season_id like 2627 means 2026/27. status: scheduled, finished, pending (kickoff passed, result not yet published). result: H/D/A from the home team''s view.';
comment on column public.matches.home_xg is 'Sum of PitchIQ xG of the home team''s shots (penalties included, own goals excluded).';
comment on column public.matches.home_xg_understat is 'Understat''s own xG total for the home team, for comparison.';

create view public.team_matches as
select match_id, league_id, season_id, kickoff_utc, home_team_id as team_id, home_team as team,
       away_team_id as opponent_id, away_team as opponent, 'home' as venue,
       home_goals as goals_for, away_goals as goals_against, home_xg as xg_for, away_xg as xg_against,
       case result when 'H' then 'W' when 'D' then 'D' when 'A' then 'L' end as outcome,
       case result when 'H' then 3 when 'D' then 1 when 'A' then 0 end as points
from public.matches where status = 'finished'
union all
select match_id, league_id, season_id, kickoff_utc, away_team_id, away_team, home_team_id, home_team, 'away',
       away_goals, home_goals, away_xg, home_xg,
       case result when 'A' then 'W' when 'D' then 'D' when 'H' then 'L' end,
       case result when 'A' then 3 when 'D' then 1 when 'H' then 0 end
from public.matches where status = 'finished';
comment on view public.team_matches is 'Finished matches from each team''s perspective (two rows per match). outcome W/D/L, points 3/1/0.';

create view public.league_table as
select s.league_id, s.season_id, public.season_label(s.season_id) as season_label, s.team_id, t.name as team,
       s.position, s.played, s.w as won, s.d as drawn, s.l as lost, s.gf as goals_for, s.ga as goals_against,
       s.gd as goal_difference, s.pts as points, s.xg_for, s.xg_against, s.xpts as expected_points,
       s.xpts_position as expected_points_position, s.pts_minus_xpts as points_minus_expected
from core.season_table s join core.teams t using (team_id);
comment on view public.league_table is 'League table with expected points. expected_points sums, over matches, the simulated expected points from shot-level xG (10,000 simulations per match). points_minus_expected > 0 means a team has over-performed its chances.';

create view public.team_elo as
select e.team_id, t.name as team, e.valid_from, e.valid_to, e.elo
from core.elo e join core.teams t using (team_id);
comment on view public.team_elo is 'ClubElo rating of each club, valid from valid_from to valid_to (inclusive).';

-- ------------------------------------------------------------------ shots and players
create view public.shots as
select s.shot_id, s.match_id, m.league_id, m.season_id, m.kickoff_utc, s.team_id, t.name as team, s.side,
       s.player_id, p.name as player, s.minute, s.x_m, s.y_m, s.distance_m, s.angle_rad,
       s.situation, s.shot_type, s.last_action, s.result, s.is_goal, s.xg, s.xg_understat
from core.shots s
join core.matches m using (match_id)
join core.teams t on t.team_id = s.team_id
left join core.players p using (player_id);
comment on view public.shots is 'Every shot. x_m: metres from the shooting team''s own goal line towards the attacked goal (0-105); y_m: metres across (0-68). situation: OpenPlay, FromCorner, SetPiece, DirectFreekick, Penalty. result: Goal, SavedShot, MissedShots, BlockedShot, ShotOnPost, OwnGoal. xg is PitchIQ xG (null for own goals). Non-penalty means situation <> ''Penalty''.';

create view public.player_seasons as
select ps.player_id, p.name as player, ps.season_id, public.season_label(ps.season_id) as season_label,
       ps.league_id, ps.team_id, t.name as team, ps.team_names, ps.position_group, ps.age, ps.nation,
       ps.games, ps.minutes, ps.goals, ps.np_goals, ps.assists, ps.shots, ps.key_passes,
       ps.xg, ps.npxg, ps.xa, ps.xg_chain, ps.xg_buildup, ps.yellow_cards, ps.red_cards,
       round((ps.npxg * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as npxg_per90,
       round((ps.xg * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as xg_per90,
       round((ps.xa * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as xa_per90,
       round((ps.goals * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as goals_per90,
       round((ps.np_goals * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as np_goals_per90,
       round((ps.assists * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as assists_per90,
       round((ps.shots * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as shots_per90,
       round((ps.key_passes * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as key_passes_per90,
       round((ps.xg_chain * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as xg_chain_per90,
       round((ps.xg_buildup * 90.0 / nullif(ps.minutes, 0))::numeric, 3) as xg_buildup_per90,
       round((ps.goals - ps.xg)::numeric, 2) as goals_minus_xg
from core.player_season ps
join core.players p using (player_id)
left join core.teams t on t.team_id = ps.team_id;
comment on view public.player_seasons is 'Season totals per player and league (Understat), with per-90 rates. position_group: FW forward, AMW attacking midfielder/winger, CM central/defensive midfielder, DEF defender, GK goalkeeper. age is age at the start of the season (from FBref, may be null). xg here is Understat xG. npxg = non-penalty xG.';

create view public.player_matches as
select pm.match_id, m.kickoff_utc, m.league_id, m.season_id, pm.player_id, p.name as player, pm.team_id,
       t.name as team, pm.position, pm.minutes, pm.goals, pm.own_goals, pm.assists, pm.shots, pm.key_passes,
       pm.xg, pm.xa, pm.xg_chain, pm.xg_buildup, pm.yellow_cards, pm.red_cards
from core.player_match pm
join core.matches m using (match_id)
join core.teams t on t.team_id = pm.team_id
left join core.players p using (player_id);
comment on view public.player_matches is 'One row per player appearance (Understat match stats; xg is Understat xG).';

create view public.player_percentiles as
select pp.player_id, p.name as player, pp.season_id, pp.league_id, pp.position_group, pp.metric, pp.per90, pp.percentile
from core.player_percentiles pp join core.players p using (player_id);
comment on view public.player_percentiles is 'Per-90 percentile (0-100) of each player among same-season, same-position-group players with at least 900 minutes, across all five leagues.';

create view public.similar_players as
select s.player_id, p.name as player, s.season_id, s.league_id, s.rank, s.other_player_id,
       o.name as other_player, s.other_league_id, s.similarity
from core.player_similar s
join core.players p on p.player_id = s.player_id
join core.players o on o.player_id = s.other_player_id;
comment on view public.similar_players is 'Top-10 most similar players (cosine similarity of standardised per-90 profiles, same season and position group).';

-- ------------------------------------------------------------------ predictions
create view public.latest_predictions as
select distinct on (match_id, model) match_id, model, created_utc, p_home, p_draw, p_away,
       exp_home_goals, exp_away_goals, top_score, score_grid
from core.predictions
order by match_id, model, created_utc desc;
comment on view public.latest_predictions is 'Most recent pre-kickoff prediction per match and model (dixon_coles, gbm, ensemble). Predictions are never stored after kickoff.';

create view public.fixtures as
with cfg as (
  select max(value) filter (where key = 'upset_min_model_prob') as upset_p,
         max(value) filter (where key = 'upset_min_edge') as upset_edge
  from core.site_settings
), pre as (
  select distinct on (match_id) match_id, bookmaker, odds_h, odds_d, odds_a, p_h, p_d, p_a
  from core.odds where kind = 'pre' order by match_id, (bookmaker = 'market_avg') desc
)
select m.match_id, m.league_id, m.league_name, m.season_id, m.kickoff_utc, m.status,
       m.home_team_id, m.home_team, m.away_team_id, m.away_team,
       p.p_home, p.p_draw, p.p_away, p.exp_home_goals, p.exp_away_goals, p.top_score, p.score_grid,
       p.created_utc as predicted_at,
       o.bookmaker as odds_source, o.odds_h, o.odds_d, o.odds_a,
       o.p_h as book_p_home, o.p_d as book_p_draw, o.p_a as book_p_away,
       greatest(p.p_home - o.p_h, p.p_draw - o.p_d, p.p_away - o.p_a) as max_edge,
       case greatest(p.p_home - o.p_h, p.p_draw - o.p_d, p.p_away - o.p_a)
         when p.p_home - o.p_h then 'H' when p.p_draw - o.p_d then 'D' else 'A' end as edge_outcome,
       coalesce(
         (o.p_h < o.p_a and p.p_home >= cfg.upset_p and p.p_home - o.p_h >= cfg.upset_edge)
         or (o.p_a < o.p_h and p.p_away >= cfg.upset_p and p.p_away - o.p_a >= cfg.upset_edge),
         false) as upset_alert
from public.matches m
cross join cfg
left join public.latest_predictions p on p.match_id = m.match_id and p.model = 'ensemble'
left join pre o on o.match_id = m.match_id
where m.status = 'scheduled';
comment on view public.fixtures is 'Upcoming matches with the ensemble prediction and the latest pre-match bookmaker probabilities (margin removed). max_edge = largest model minus bookmaker probability; upset_alert flags matches where the model rates the bookmaker underdog much higher.';

create view public.prediction_track_record as
with book as (
  select distinct on (match_id) match_id, bookmaker, p_h, p_d, p_a
  from core.odds where kind = 'closing' order by match_id, (bookmaker = 'pinnacle') desc
), j as (
  select m.match_id, m.league_id, m.season_id, m.kickoff_utc, m.home_team, m.away_team, m.home_goals, m.away_goals,
         m.result, p.model, p.created_utc as predicted_at, p.p_home, p.p_draw, p.p_away,
         b.bookmaker as closing_source, b.p_h as book_p_home, b.p_d as book_p_draw, b.p_a as book_p_away,
         (m.result = 'H')::int as oh, (m.result = 'D')::int as od, (m.result = 'A')::int as oa
  from public.matches m
  join public.latest_predictions p using (match_id)
  left join book b using (match_id)
  where m.status = 'finished'
)
select match_id, league_id, season_id, kickoff_utc, home_team, away_team, home_goals, away_goals, result, model,
       predicted_at, p_home, p_draw, p_away, closing_source, book_p_home, book_p_draw, book_p_away,
       -ln(greatest(p_home * oh + p_draw * od + p_away * oa, 1e-12)) as log_loss,
       power(p_home - oh, 2) + power(p_draw - od, 2) + power(p_away - oa, 2) as brier,
       (power(p_home - oh, 2) + power(p_home + p_draw - oh - od, 2)) / 2 as rps,
       -ln(greatest(book_p_home * oh + book_p_draw * od + book_p_away * oa, 1e-12)) as book_log_loss,
       power(book_p_home - oh, 2) + power(book_p_draw - od, 2) + power(book_p_away - oa, 2) as book_brier,
       (power(book_p_home - oh, 2) + power(book_p_home + book_p_draw - oh - od, 2)) / 2 as book_rps
from j;
comment on view public.prediction_track_record is 'Live track record: the last prediction made before kickoff for every finished match, scored with log loss, Brier and ranked probability score (lower is better), next to bookmaker closing odds.';

create view public.backtest_results as
select scope, league_id, season_id, model, n as matches, log_loss, brier, rps from core.backtest_summary;
comment on view public.backtest_results is 'Walk-forward backtest (no future data) of each model and of bookmaker closing odds. scope all = pooled over leagues and seasons.';

create view public.calibration as select family, model, outcome, bin, mean_pred, obs_freq, n from core.calibration;
create view public.model_meta as select name, meta, updated_at from core.model_meta;
create view public.freshness as select doc, updated_at from core.freshness;

-- ------------------------------------------------------------------ privileges
-- Simple views are auto-updatable: strip the default ALL grants, then allow SELECT only.
revoke all on all tables in schema public from anon, authenticated;
grant select on all tables in schema public to anon, authenticated;
