"""Integration test: migrations + publish + the public security model, against a real Postgres.

Runs when ``PITCHIQ_TEST_PG_DSN`` points at a Postgres superuser connection (CI uses the
``pgvector/pgvector`` service image). Without pgvector, a tiny cosine-distance shim stands in.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("PITCHIQ_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="PITCHIQ_TEST_PG_DSN not set")
MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
DB = "pitchiq_test"

VECTOR_SHIM = """
create schema if not exists extensions;
create function extensions.cosdist(a text, b text) returns float8 language sql immutable as $$
  select 1 - sum(x * y) / nullif(sqrt(sum(x * x)) * sqrt(sum(y * y)), 0)
  from unnest(translate(a, '[]', '{}')::float8[], translate(b, '[]', '{}')::float8[]) as t(x, y) $$;
create operator extensions.<=> (leftarg = text, rightarg = text, function = extensions.cosdist);
"""


def _dsn(db: str) -> str:
    return (
        re.sub(r"/[^/?]*(\?|$)", f"/{db}\\1", DSN, count=1) if DSN.count("/") > 2 else f"{DSN}/{db}"
    )


@pytest.fixture(scope="module")
def db():
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {DB} with (force)")
        admin.execute(f"create database {DB}")
    conn = psycopg.connect(_dsn(DB), autocommit=True)
    for role in ("anon", "authenticated", "service_role"):
        conn.execute(
            f"do $$ begin if not exists (select from pg_roles where rolname = '{role}') then create role {role} nologin; end if; end $$"
        )
    has_vector = (
        conn.execute(
            "select count(*) from pg_available_extensions where name = 'vector'"
        ).fetchone()[0]
        > 0
    )
    conn.execute("create schema if not exists extensions")
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text()
        if not has_vector:
            sql = sql.replace(
                "create extension if not exists vector with schema extensions;", VECTOR_SHIM
            )
            sql = sql.replace("extensions.vector(9)", "text")
        conn.execute(sql)
    conn.execute("alter role pipeline_writer password 'test'")
    conn.execute("insert into core.app_secrets values ('ask_server_token', 'tok')")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def published(db, ingested, cfg):
    from pitchiq.models import similarity, xpts
    from pitchiq.publish.supabase import publish

    store, _, _ = ingested
    settings, leagues = cfg
    shots = store.read("shots")
    store.write(
        "shots_xg",
        pd.DataFrame({"shot_id": shots["shot_id"], "xg": shots["xg_us"], "xg_bt": shots["xg_us"]}),
    )
    xpts.run(store, settings.xpts, ["2425", "2526"])
    similarity.run(
        store, settings.similarity.model_copy(update={"min_minutes": 1}), ["2425", "2526"]
    )
    m = store.read("matches")
    nxt = m[m["status"] == "scheduled"].iloc[0]
    store.write(
        "predictions",
        pd.DataFrame(
            [
                {
                    "match_id": nxt["match_id"],
                    "model": "ensemble",
                    "created_utc": nxt["kickoff_utc"] - pd.Timedelta(days=1),
                    "p_home": 0.5,
                    "p_draw": 0.3,
                    "p_away": 0.2,
                    "exp_home_goals": 1.5,
                    "exp_away_goals": 1.0,
                    "top_score": "1-0",
                    "score_grid": "[[0.1]]",
                }
            ]
        ),
    )
    settings = settings.model_copy(deep=True)
    settings.seasons.db_window = 2
    writer = re.sub(r"//[^@/]*@", "//pipeline_writer:test@", _dsn(DB)) if "@" in DSN else _dsn(DB)
    counts = publish(store, settings, leagues, dsn=writer)
    counts2 = publish(store, settings, leagues, dsn=writer)  # idempotent
    return counts, counts2


def test_publish_counts_and_idempotency(published, db):
    counts, counts2 = published
    assert counts["matches"] == 24 and counts["shots"] > 0
    assert {k: v for k, v in counts.items() if k != "database_size_mb"} == {
        k: v for k, v in counts2.items() if k != "database_size_mb"
    }
    assert db.execute("select count(*) from core.matches").fetchone()[0] == 24
    assert db.execute("select count(*) from core.predictions").fetchone()[0] == 1


def test_anon_reads_views_but_cannot_write(published, db):
    with db.transaction():
        db.execute("set local role anon")
        assert db.execute("select count(*) from public.league_table").fetchone()[0] == 8
        assert (
            db.execute("select count(*) from public.fixtures where p_home is not null").fetchone()[
                0
            ]
            == 1
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("insert into public.leagues values ('XXX1', 'x', 'x', 2)")


def test_anon_cannot_touch_core(published, db):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
        db.execute("set local role anon")
        db.execute("select * from core.matches")


def test_ask_execute_guardrails(published, db):
    with db.transaction():
        db.execute("set local role anon")
        rows = db.execute(
            "select public.ask_execute('select team, points from league_table order by points desc', 3)"
        ).fetchone()[0]
        assert len(rows) == 3
    for bad in (
        "drop table core.matches",
        "select 1; delete from core.matches",
        "select pg_sleep(10)",
        "select * from core.matches",
    ):
        with pytest.raises(psycopg.Error), db.transaction():
            db.execute("set local role anon")
            db.execute("select public.ask_execute(%s)", (bad,))


def test_quota_requires_server_token(published, db):
    with db.transaction():
        db.execute("set local role anon")
        assert db.execute("select public.ask_consume_quota('tok', 10)").fetchone()[0] == 9
    with pytest.raises(psycopg.Error), db.transaction():
        db.execute("set local role anon")
        db.execute("select public.ask_consume_quota('wrong', 10)")


def test_scout_similar(published, db):
    pid, season = db.execute(
        "select player_id, season_id from core.player_embeddings limit 1"
    ).fetchone()
    with db.transaction():
        db.execute("set local role anon")
        rows = db.execute(
            "select * from public.scout_similar(%s, %s, null, null, 0, 5)", (pid, season)
        ).fetchall()
    assert rows and all(r[0] != pid for r in rows)


def test_trigger_rejects_post_kickoff_prediction(published, db):
    mid, ko = db.execute(
        "select match_id, kickoff_utc from core.matches where status = 'finished' limit 1"
    ).fetchone()
    with pytest.raises(psycopg.Error), db.transaction():
        db.execute(
            "insert into core.predictions (match_id, model, created_utc, p_home, p_draw, p_away) values (%s, 'ensemble', %s, .4, .3, .3)",
            (mid, ko),
        )
