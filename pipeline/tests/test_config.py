import pytest

from pitchiq.config import load_leagues, load_settings, season_range


def test_leagues_load_and_cover_top5():
    ids = {lg.league_id for lg in load_leagues().leagues}
    assert ids == {"ENG1", "ESP1", "GER1", "ITA1", "FRA1"}


def test_ligue1_team_count_history():
    fra = next(lg for lg in load_leagues().leagues if lg.league_id == "FRA1")
    assert fra.teams_in_season("2223") == 20
    assert fra.teams_in_season("2627") == 18


def test_settings_load():
    s = load_settings()
    assert s.seasons.current == "2627"
    assert s.xpts["n_sims"] > 0


def test_season_range():
    assert season_range("1415", "1617") == ["1415", "1516", "1617"]
    assert len(season_range("1415", "2627")) == 13
    with pytest.raises(ValueError):
        season_range("2627", "1415")
