-- Roles and RPC functions: Scout similarity search, the guarded Ask SQL executor,
-- and the Ask agent's daily request cap.

-- ------------------------------------------------------------------ pipeline writer
do $$ begin
  if not exists (select from pg_roles where rolname = 'pipeline_writer') then
    create role pipeline_writer login noinherit;   -- password is set out-of-band, never in git
  end if;
end $$;
grant usage on schema core to pipeline_writer;
grant select, insert, update, delete, truncate on all tables in schema core to pipeline_writer;
grant usage on all sequences in schema core to pipeline_writer;
alter default privileges in schema core grant select, insert, update, delete, truncate on tables to pipeline_writer;
alter role pipeline_writer set statement_timeout = '10min';

-- ------------------------------------------------------------------ Scout
create function public.scout_similar(
  p_player_id bigint,
  p_season_id text,
  p_league_id text default null,
  p_max_age real default null,
  p_min_minutes integer default 900,
  p_limit integer default 20
) returns table (
  player_id bigint, player text, team text, league_id text, position_group text,
  age real, minutes integer, similarity real
)
language sql stable security definer set search_path = '' as $$
  with target as (
    select e.embedding, e.position_group from core.player_embeddings e
    where e.player_id = p_player_id and e.season_id = p_season_id
    order by e.minutes desc limit 1
  )
  select e.player_id, pl.name, t.name, e.league_id, e.position_group, e.age, e.minutes,
         (1 - (e.embedding operator(extensions.<=>) target.embedding))::real
  from core.player_embeddings e
  cross join target
  join core.players pl on pl.player_id = e.player_id
  left join core.teams t on t.team_id = e.team_id
  where e.season_id = p_season_id
    and e.position_group = target.position_group
    and e.player_id <> p_player_id
    and (p_league_id is null or e.league_id = p_league_id)
    and (p_max_age is null or e.age <= p_max_age)
    and e.minutes >= coalesce(p_min_minutes, 0)
  order by e.embedding operator(extensions.<=>) target.embedding
  limit least(greatest(coalesce(p_limit, 20), 1), 50)
$$;
comment on function public.scout_similar is 'Players most similar to p_player_id in the same season and position group, with optional league / max age / min minutes filters.';

-- ------------------------------------------------------------------ Ask: read-only executor
do $$ begin
  if not exists (select from pg_roles where rolname = 'ask_reader') then
    create role ask_reader nologin;
  end if;
end $$;
grant usage on schema public to ask_reader;
grant select on all tables in schema public to ask_reader;
grant ask_reader to postgres;
grant create on schema public to ask_reader;     -- needed to own the function below

-- Defence in depth (the web app also parses the SQL and allows a single SELECT):
--  * the function runs as ask_reader, which can only SELECT the public views;
--  * statement_timeout caps runtime; the wrapper caps rows; ';' cannot escape the subquery;
--  * PostgREST calls it in a read-only transaction (GET).
create function public.ask_execute(query text, max_rows integer default 200)
returns jsonb
language plpgsql stable security definer
set search_path = public
set statement_timeout = '5s'
as $$
declare
  result jsonb;
begin
  if query ~* '\m(insert|update|delete|merge|drop|alter|create|grant|revoke|truncate|copy|call|do|set|reset|listen|notify|vacuum|analyze|refresh|lock|comment|prepare|execute|pg_sleep|pg_read_file|pg_ls_dir|lo_import|lo_export|dblink)\M'
     or query ~ ';' then
    raise exception 'only a single read-only SELECT is allowed';
  end if;
  execute format(
    'select coalesce(jsonb_agg(t), ''[]''::jsonb) from (select * from (%s) as q limit %s) as t',
    query, least(greatest(coalesce(max_rows, 200), 1), 200)
  ) into result;
  return result;
end $$;
alter function public.ask_execute(text, integer) owner to ask_reader;
revoke create on schema public from ask_reader;
revoke all on function public.ask_execute(text, integer) from public;
grant execute on function public.ask_execute(text, integer) to anon, authenticated;

-- ------------------------------------------------------------------ Ask: quota + log (server token required)
create function public.ask_consume_quota(token text, daily_cap integer)
returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare
  used integer;
begin
  if token is distinct from (select value from core.app_secrets where name = 'ask_server_token') then
    raise exception 'unauthorised';
  end if;
  insert into core.ask_usage as u (day, n_requests) values ((now() at time zone 'utc')::date, 1)
  on conflict (day) do update set n_requests = u.n_requests + 1
  returning n_requests into used;
  return daily_cap - used;   -- negative => over the cap
end $$;

create function public.ask_log_insert(
  token text, p_question text, p_sql text, p_ok boolean, p_n_rows integer, p_latency_ms integer, p_error text
) returns void
language plpgsql volatile security definer set search_path = '' as $$
begin
  if token is distinct from (select value from core.app_secrets where name = 'ask_server_token') then
    raise exception 'unauthorised';
  end if;
  insert into core.ask_log (question, sql, ok, n_rows, latency_ms, error)
  values (left(p_question, 500), left(p_sql, 4000), p_ok, p_n_rows, p_latency_ms, left(p_error, 500));
  delete from core.ask_log where asked_at < now() - interval '30 days';
end $$;

revoke all on function public.ask_consume_quota(text, integer) from public;
revoke all on function public.ask_log_insert(text, text, text, boolean, integer, integer, text) from public;
grant execute on function public.ask_consume_quota(text, integer) to anon, authenticated;
grant execute on function public.ask_log_insert(text, text, text, boolean, integer, integer, text) to anon, authenticated;
revoke all on function public.scout_similar(bigint, text, text, real, integer, integer) from public;
grant execute on function public.scout_similar(bigint, text, text, real, integer, integer) to anon, authenticated;
grant execute on function public.season_label(text) to anon, authenticated, ask_reader;
