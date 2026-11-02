import pandas as pd

from pitchiq.canonical.players import match_team_players, name_score


def test_name_score_handles_accents_and_order():
    assert name_score("Kylian Mbappé-Lottin", "Kylian Mbappe") > 85
    assert name_score("Son Heung-Min", "Heung-min Son") > 85
    assert name_score("Bruno Fernandes", "Bruno Guimarães") < 85


def test_team_assignment_is_one_to_one():
    us = pd.DataFrame({"player_name": ["Gabriel", "Gabriel Martinelli", "Gabriel Jesus"]})
    fb = pd.DataFrame(
        {"fbref_player": ["Gabriel Jesus", "Gabriel Magalhães", "Gabriel Martinelli"]}
    )
    pairs = match_team_players(us, fb, 60)
    got = {us.loc[u, "player_name"]: fb.loc[f, "fbref_player"] for u, f, _ in pairs}
    assert got["Gabriel Martinelli"] == "Gabriel Martinelli"
    assert got["Gabriel Jesus"] == "Gabriel Jesus"
    assert got.get("Gabriel") in (None, "Gabriel Magalhães")
