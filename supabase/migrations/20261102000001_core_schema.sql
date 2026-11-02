-- PitchIQ core schema. Tables live in `core` (not exposed by the Data API);
-- the website and the Ask agent only see the documented views in `public`.

create extension if not exists vector with schema extensions;

create schema if not exists core;
revoke all on schema core from public, anon, authenticated;

-- ------------------------------------------------------------------ reference
create table core.leagues (
  league_id text primary key,
  name text not null,
  country text not null,
  n_teams smallint not null
);

create table core.teams (
  team_id text primary key,
  name text not null,
  league_id text not null references core.leagues,
  country text not null
);

create table core.players (
  player_id bigint primary key,           -- Understat player id (canonical)
  name text not null,
  team_id text references core.teams,
  league_id text references core.leagues,
  last_season_id text,
  position_group text check (position_group in ('FW', 'AMW', 'CM', 'DEF', 'GK')),
  born smallint,
  nation text
);

-- ------------------------------------------------------------------ matches
create table core.matches (
  match_id bigint primary key,            -- Understat match id
  league_id text not null references core.leagues,
  season_id text not null check (season_id ~ '^\d{4}$'),
  kickoff_utc timestamptz not null,
  home_team_id text not null references core.teams,
  away_team_id text not null references core.teams,
  status text not null check (status in ('scheduled', 'finished', 'pending')),
  home_goals smallint check (home_goals between 0 and 20),
  away_goals smallint check (away_goals between 0 and 20),
  home_xg real,                           -- PitchIQ xG
  away_xg real,
  home_xg_understat real,
  away_xg_understat real,
  check (home_team_id <> away_team_id)
);
create index on core.matches (league_id, season_id, kickoff_utc);
create index on core.matches (home_team_id, kickoff_utc);
create index on core.matches (away_team_id, kickoff_utc);
create index on core.matches (kickoff_utc);

create table core.odds (
  match_id bigint not null references core.matches on delete cascade,
  bookmaker text not null check (bookmaker in ('pinnacle', 'market_avg')),
  kind text not null check (kind in ('pre', 'closing')),
  odds_h real not null check (odds_h > 1),
  odds_d real not null check (odds_d > 1),
  odds_a real not null check (odds_a > 1),
  p_h real not null, p_d real not null, p_a real not null,   -- margin removed (Shin)
  overround real not null,
  captured_at timestamptz not null,
  primary key (match_id, bookmaker, kind)
);

create table core.shots (
  shot_id bigint primary key,
  match_id bigint not null references core.matches on delete cascade,
  team_id text not null references core.teams,
  player_id bigint not null,
  side char(1) not null check (side in ('h', 'a')),
  minute smallint not null,
  x_m real not null,                      -- metres from own goal line (0..105)
  y_m real not null,                      -- metres across (0..68)
  distance_m real not null,
  angle_rad real not null,
  situation text not null,
  shot_type text not null,
  last_action text,
  result text not null,
  is_goal boolean not null,
  xg real,                                -- PitchIQ xG (null for own goals)
  xg_understat real
);
create index on core.shots (match_id);
create index on core.shots (player_id);

create table core.player_match (
  match_id bigint not null references core.matches on delete cascade,
  player_id bigint not null,
  team_id text not null references core.teams,
  position text,
  minutes smallint not null,
  goals smallint not null, own_goals smallint not null, assists smallint not null,
  shots smallint not null, key_passes smallint not null,
  yellow_cards smallint not null, red_cards smallint not null,
  xg real not null, xa real not null, xg_chain real not null, xg_buildup real not null,
  primary key (match_id, player_id)
);
create index on core.player_match (player_id);

create table core.player_season (
  player_id bigint not null,
  season_id text not null,
  league_id text not null references core.leagues,
  team_id text references core.teams,
  team_names text,
  position_group text,
  games smallint, minutes integer,
  goals smallint, np_goals smallint, assists smallint, shots smallint, key_passes smallint,
  yellow_cards smallint, red_cards smallint,
  xg real, npxg real, xa real, xg_chain real, xg_buildup real,
  age real, nation text,
  primary key (player_id, season_id, league_id)
);

create table core.elo (
  team_id text not null references core.teams,
  valid_from date not null,
  valid_to date not null,
  elo real not null check (elo between 500 and 2500),
  primary key (team_id, valid_from)
);

-- ------------------------------------------------------------------ models
create table core.xpts_match (
  match_id bigint not null references core.matches on delete cascade,
  team_id text not null references core.teams,
  side char(1) not null,
  p_win real not null, p_draw real not null, p_loss real not null,
  xpts real not null, xg_for real not null, xg_against real not null, n_sims integer not null,
  primary key (match_id, team_id)
);

create table core.season_table (
  league_id text not null, season_id text not null, team_id text not null references core.teams,
  position smallint, xpts_position smallint,
  played smallint, w smallint, d smallint, l smallint, gf smallint, ga smallint, gd smallint, pts smallint,
  xg_for real, xg_against real, xpts real, pts_minus_xpts real,
  primary key (league_id, season_id, team_id)
);

create table core.predictions (
  match_id bigint not null references core.matches on delete cascade,
  model text not null check (model in ('dixon_coles', 'gbm', 'ensemble')),
  created_utc timestamptz not null,
  p_home real not null, p_draw real not null, p_away real not null,
  exp_home_goals real, exp_away_goals real, top_score text,
  score_grid jsonb,
  primary key (match_id, model, created_utc)
);

-- A prediction may never be stored for a match that has already kicked off.
create function core.reject_post_kickoff_prediction() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.created_utc >= (select kickoff_utc from core.matches where match_id = new.match_id) then
    raise exception 'prediction for match % created at or after kickoff', new.match_id;
  end if;
  return new;
end $$;
create trigger predictions_before_kickoff before insert or update on core.predictions
  for each row execute function core.reject_post_kickoff_prediction();

create table core.backtest_summary (
  scope text not null, league_id text not null, season_id text not null, model text not null,
  n integer not null, log_loss real not null, brier real not null, rps real not null,
  primary key (scope, league_id, season_id, model)
);

create table core.calibration (
  family text not null,                   -- 'predictor' | 'xg'
  model text not null, outcome text not null, bin smallint not null,
  mean_pred real not null, obs_freq real not null, n integer not null,
  primary key (family, model, outcome, bin)
);

create table core.model_meta (
  name text primary key,                  -- 'xg', 'predictor', 'player_link'
  meta jsonb not null,
  updated_at timestamptz not null default now()
);

create table core.player_embeddings (
  player_id bigint not null, season_id text not null, league_id text not null,
  team_id text, position_group text not null, minutes integer not null, age real,
  embedding extensions.vector(9) not null,
  primary key (player_id, season_id, league_id)
);

create table core.player_similar (
  player_id bigint not null, season_id text not null, league_id text not null, rank smallint not null,
  other_player_id bigint not null, other_league_id text not null, similarity real not null,
  primary key (player_id, season_id, league_id, rank)
);

create table core.player_percentiles (
  player_id bigint not null, season_id text not null, league_id text not null,
  position_group text not null, metric text not null, per90 real, percentile real,
  primary key (player_id, season_id, league_id, metric)
);

create table core.freshness (
  id boolean primary key default true check (id),
  doc jsonb not null,
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ Ask agent bookkeeping
create table core.app_secrets (name text primary key, value text not null);
create table core.ask_usage (day date primary key, n_requests integer not null default 0);
create table core.ask_log (
  id bigint generated always as identity primary key,
  asked_at timestamptz not null default now(),
  question text not null, sql text, ok boolean not null, n_rows integer, latency_ms integer, error text
);
