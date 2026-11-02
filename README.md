# PitchIQ

Football analytics for Europe's top 5 leagues: match predictions, an in-house xG model,
expected-points tables, player similarity search and a natural-language "Ask" agent.
It updates daily and runs entirely on free tiers.

> **Status:** Phase 0 (planning). See [`docs/phase-0-plan.md`](docs/phase-0-plan.md).

## Repository layout

| Path | What |
|---|---|
| `pipeline/` | Python 3.11 package: ingestion, validation, models |
| `web/` | Next.js site (Phase 6) |
| `supabase/migrations/` | Postgres schema (Phase 5) |
| `ledger/predictions/` | Append-only, timestamped pre-kickoff predictions |
| `docs/` | Plan, methodology, data sources |

## Data sources

Credited in full on the site's About page: [football-data.co.uk](https://www.football-data.co.uk),
[Understat](https://understat.com), [ClubElo](http://clubelo.com), [FBref](https://fbref.com),
accessed via [soccerdata](https://github.com/probberechts/soccerdata).
