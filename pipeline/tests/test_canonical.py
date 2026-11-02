from pitchiq.canonical.teams import assign_names, load_aliases, make_team_id, normalise


def test_normalise_strips_noise_and_accents():
    assert normalise("FC Köln") == "koln"
    assert normalise("Paris Saint-Germain FC") == "paris saint germain"


def test_team_id():
    assert make_team_id("Germany", "Borussia M.Gladbach") == "ger-borussia-m-gladbach"


def test_assignment_resolves_hard_names_by_elimination():
    targets = {
        "esp-athletic-club": "Athletic Club",
        "esp-atletico-madrid": "Atletico Madrid",
        "esp-real-madrid": "Real Madrid",
        "esp-real-betis": "Real Betis",
    }
    got = {
        m.source_name: m.team_id
        for m in assign_names(
            ["Ath Bilbao", "Ath Madrid", "Real Madrid", "Betis"], targets, load_aliases()
        )
    }
    assert got == {
        "Ath Bilbao": "esp-athletic-club",
        "Ath Madrid": "esp-atletico-madrid",
        "Real Madrid": "esp-real-madrid",
        "Betis": "esp-real-betis",
    }
