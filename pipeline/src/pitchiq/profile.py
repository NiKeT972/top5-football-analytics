"""A compact, human-readable profile of the processed data (row counts, coverage, category values).

Printed by CI so a run's data can be inspected from the job log without downloading it.
Only aggregates are printed, never raw rows.
"""

from __future__ import annotations

from pitchiq.storage.parquet import Store


def profile_markdown(store: Store) -> str:
    """Return a markdown profile of the processed tables."""
    con = store.duckdb()
    tables = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY 1"
        ).fetchall()
    ]
    out = ["## Data profile", "", "| table | rows |", "|---|---|"]
    for t in tables:
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        out.append(f"| {t} | {n:,} |")

    def q(title: str, sql: str) -> None:
        needed = {
            w
            for w in sql.replace("(", " ").replace(")", " ").split()
            if w in {"matches", "shots", "odds", "elo", "player_season"}
        }
        if not needed <= set(tables):
            return
        df = con.execute(sql).df()
        out.extend(["", f"### {title}", "", df.to_markdown(index=False)])

    q(
        "Matches per league-season",
        "SELECT league_id, season_id, count(*) AS matches, sum((status='finished')::int) AS finished "
        "FROM matches GROUP BY ALL ORDER BY season_id DESC, league_id LIMIT 30",
    )
    q(
        "Shot coverage per season",
        "SELECT m.season_id, count(DISTINCT s.match_id) AS matches_with_shots, count(*) AS shots, "
        "round(avg(s.xg_us), 4) AS mean_xg, round(avg((s.result='Goal')::int), 4) AS goal_rate "
        "FROM shots s JOIN matches m USING (match_id) GROUP BY ALL ORDER BY 1",
    )
    for col in ("situation", "shot_type", "result", "last_action"):
        q(
            f"shots.{col}",
            f"SELECT {col}, count(*) AS n FROM shots GROUP BY ALL ORDER BY n DESC LIMIT 25",
        )
    q(
        "Own-goal side convention check",
        "WITH g AS (SELECT match_id, "
        "sum((result='Goal' AND side='h')::int) gh, sum((result='Goal' AND side='a')::int) ga, "
        "sum((result='OwnGoal' AND side='h')::int) oh, sum((result='OwnGoal' AND side='a')::int) oa "
        "FROM shots GROUP BY 1) "
        "SELECT avg((gh+oh=m.home_goals AND ga+oa=m.away_goals)::int) AS own_goal_listed_under_beneficiary, "
        "avg((gh+oa=m.home_goals AND ga+oh=m.away_goals)::int) AS own_goal_listed_under_scorer_team, "
        "count(*) AS n FROM g JOIN matches m USING (match_id)",
    )
    q("Odds coverage", "SELECT bookmaker, kind, count(*) AS n FROM odds GROUP BY ALL ORDER BY 1, 2")
    q(
        "Elo coverage",
        "SELECT count(DISTINCT team_id) AS teams, min(valid_from) AS first, max(valid_to) AS last FROM elo",
    )
    q(
        "Position groups (player_season)",
        "SELECT position_group, count(*) AS n, sum((minutes>=900)::int) AS n_900 FROM player_season GROUP BY ALL ORDER BY n DESC",
    )
    return "\n".join(out)
