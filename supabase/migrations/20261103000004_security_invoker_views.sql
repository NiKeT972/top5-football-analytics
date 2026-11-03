-- Views run with the caller's privileges (security_invoker) instead of the owner's.
-- Readers get SELECT on the public football-data tables in `core` only; secrets and the
-- Ask bookkeeping tables stay unreadable. `core` is not exposed by the Data API, so these
-- tables are still only reachable through the documented views and RPC functions.

do $$
declare v text;
begin
  foreach v in array array[
    'leagues','teams','matches','team_matches','league_table','team_elo','shots','player_seasons',
    'player_matches','player_percentiles','similar_players','latest_predictions','fixtures',
    'prediction_track_record','backtest_results','calibration','model_meta','freshness'
  ] loop
    execute format('alter view public.%I set (security_invoker = true)', v);
  end loop;
end $$;

grant usage on schema core to anon, authenticated, ask_reader;
grant select on
  core.leagues, core.teams, core.players, core.matches, core.odds, core.shots, core.player_match,
  core.player_season, core.elo, core.xpts_match, core.season_table, core.predictions,
  core.backtest_summary, core.calibration, core.model_meta, core.player_embeddings,
  core.player_similar, core.player_percentiles, core.freshness, core.site_settings
  to anon, authenticated, ask_reader;
-- Explicitly never readable by API roles:
revoke all on core.app_secrets, core.ask_usage, core.ask_log from anon, authenticated, ask_reader;
