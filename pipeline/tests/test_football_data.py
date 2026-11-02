from pitchiq.ingest.football_data import parse_csv


def test_parse_legacy_average_columns_and_two_digit_years():
    raw = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,BbAvH,BbAvD,BbAvA,PSCH,PSCD,PSCA\nE0,16/08/14,Arsenal,Crystal Palace,2,1,1.25,5.9,12.5,1.26,6.2,13.1\n"
    df = parse_csv(raw)
    assert str(df.loc[0, "date"]) == "2014-08-16"
    assert df.loc[0, "odds_market_avg_pre_h"] == 1.25
    assert df.loc[0, "odds_pinnacle_closing_a"] == 13.1
    assert int(df.loc[0, "home_goals"]) == 2
