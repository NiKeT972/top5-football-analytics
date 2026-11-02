import pandas as pd

from pitchiq.validate.checks import validate_all
from tests.fakeworld import FD_NAMES, US_NAMES


def test_all_sources_ok(ingested):
    _, result, _ = ingested
    assert result.ok, [(s.source, s.message) for s in result.statuses]


def test_teams_have_canonical_slugs(ingested):
    store, _, _ = ingested
    teams = store.read("teams")
    assert set(teams["team_id"]) == {
        "eng-manchester-united",
        "eng-manchester-city",
        "eng-nottingham-forest",
        "eng-wolverhampton-wanderers",
    }


def test_matches_and_statuses(ingested):
    store, _, _ = ingested
    m = store.read("matches")
    assert len(m) == 24 and m["match_id"].is_unique
    assert {"finished", "scheduled"} <= set(m["status"])
    assert m.loc[m["status"] == "finished", "home_goals"].notna().all()


def test_football_data_names_map_to_understat_teams(ingested):
    store, _, _ = ingested
    mp = store.read("team_source_names_fd")
    teams = store.read("teams").set_index("us_team_id")["team_id"]
    expected = {FD_NAMES[k]: teams[k] for k in US_NAMES}
    got = dict(zip(mp["source_name"], mp["team_id"], strict=True))
    assert got == expected


def test_odds_closing_and_pre(ingested):
    store, _, _ = ingested
    odds = store.read("odds")
    m = store.read("matches").set_index("match_id")
    closing = odds[odds["kind"] == "closing"]
    assert set(m.loc[closing["match_id"], "status"]) == {"finished"}
    pre_upcoming = odds[(odds["kind"] == "pre") & odds["match_id"].map(m["status"]).eq("scheduled")]
    assert len(pre_upcoming) > 0
    assert (odds[["odds_h", "odds_d", "odds_a"]] > 1).all().all()


def test_elo_ignores_lower_division_and_covers_all_teams(ingested):
    store, _, _ = ingested
    mp = store.read("team_source_names_elo")
    assert "Leeds" not in set(mp["source_name"])
    assert store.read("elo")["team_id"].nunique() == 4


def test_shots_and_player_tables(ingested):
    store, _, _ = ingested
    shots, pm, ps = store.read("shots"), store.read("player_match"), store.read("player_season")
    fin = store.read("matches").query("status == 'finished'")
    assert set(shots["match_id"]) == set(fin["match_id"])
    assert pm.groupby("match_id").size().eq(8).all()
    assert {"FW", "CM", "DEF", "GK"} <= set(ps["position_group"])


def test_validation_passes(ingested, cfg):
    store, _, _ = ingested
    settings, leagues = cfg
    report = validate_all(store, settings, leagues)
    assert not report.failed_hard


def test_incremental_run_fetches_no_finished_match_twice(ingested, cfg, world):
    from pitchiq.ingest.run import Ingestor
    from tests.fakeworld import TODAY, FakeHTTP

    store, _, _ = ingested
    settings, leagues = cfg
    clients = {
        src: FakeHTTP(src, world, store.raw) for src in ("understat", "football_data", "clubelo")
    }
    Ingestor(store, settings, leagues, clients=clients, now=pd.Timestamp(TODAY, tz="UTC")).run()
    assert not [u for u in clients["understat"].urls if "getMatchData" in u]


def test_failed_understat_skips_dependents_and_validation_fails_cleanly(tmp_path, cfg, world):
    from pitchiq.http import SourceError
    from pitchiq.ingest.run import Ingestor
    from pitchiq.storage.parquet import Store
    from pitchiq.validate.checks import ValidationFailed
    from tests.fakeworld import TODAY, FakeHTTP

    class Down(FakeHTTP):
        def get(self, url, **kw):
            if "understat" in url:
                raise SourceError("understat", url, "ConnectTimeout")
            return super().get(url, **kw)

    settings, leagues = cfg
    store = Store(tmp_path)
    clients = {
        src: Down(src, world, store.raw) for src in ("understat", "football_data", "clubelo")
    }
    result = Ingestor(
        store, settings, leagues, clients=clients, now=pd.Timestamp(TODAY, tz="UTC")
    ).run()
    assert not result.ok
    assert all("skipped" in s.message for s in result.statuses[1:])
    try:
        validate_all(store, settings, leagues)
    except ValidationFailed:
        pass
    else:
        raise AssertionError("validation should fail without matches")
