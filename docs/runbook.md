# Runbook

## One-time setup (owner)

1. **Database secrets.** In the Supabase dashboard (project `pitchiq`) → SQL editor, run this with the values from `.secrets/pitchiq-secrets.env` (git-ignored; or generate your own):
   ```sql
   alter role pipeline_writer password '<PIPELINE_WRITER_PASSWORD>';
   insert into core.app_secrets (name, value) values ('ask_server_token', '<ASK_SERVER_TOKEN>')
   on conflict (name) do update set value = excluded.value;
   ```
2. **GitHub repository secrets** (Settings → Secrets and variables → Actions):
   - `SUPABASE_DB_URL`: the *Session pooler* URI from Supabase → Connect, with the user changed to `pipeline_writer.augllwoyczgqwikeplti` and the password from step 1.
   - `REVALIDATE_SECRET`: from `.secrets/pitchiq-secrets.env`.
   - Repository *variables*: `SITE_URL` (your Vercel URL), plus `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` for the Ask evaluation workflow.
3. **Vercel** (project `pitchiq` already exists): connect the GitHub repo, set *Root Directory* = `web`, and add the env vars listed in `web/.env.example` (Supabase URL + publishable key, `REVALIDATE_SECRET`, `ASK_SERVER_TOKEN`, `GOOGLE_GENERATIVE_AI_API_KEY`). Deploy.
4. **Free LLM key** for Ask: Google AI Studio → API key → `GOOGLE_GENERATIVE_AI_API_KEY` on Vercel (and as a GitHub secret for the eval workflow).

## Understat blocks cloud IPs

Verified on 2 Nov 2026 (`diagnose-sources.yml`): connections from GitHub-hosted runners to understat.com time out (silent drop), matching public reports of Understat blocking Google Cloud/Colab ranges. We do **not** evade the block (no proxies, Tor or VPN tricks). Instead the daily job can run on a **self-hosted runner** at home (free):

1. Repo → Settings → Actions → Runners → *New self-hosted runner*; follow the commands on a machine that is usually on (laptop, Raspberry Pi 4/5, old PC). Install as a service.
2. Set the repository variable `PITCHIQ_RUNNER` = `self-hosted`.
3. Security: the repo is public, so never let pull requests run on that runner. Only `daily.yml` (schedule / manual) uses it; CI and the weekly retrain stay on GitHub-hosted runners.

If the machine is off, the next run catches up automatically (ingestion is incremental).

## Backfill

The first run downloads ~21k Understat matches (one request each, 2 s apart). Run **Daily pipeline** manually with `max_match_requests = 8000` three times (≈4.5 h each; progress is checkpointed every 250 matches and kept in the Actions cache), then **Weekly retrain** once.

## Where the data lives

| What | Where | Durability |
|---|---|---|
| Processed Parquet store + models | GitHub Actions cache (`pitchiq-data-v1-*`) | Refreshed daily; evicted after 7 days unused → rerun backfill |
| Current + 2 previous seasons | Supabase Postgres (`core` tables, `public` views) | Durable |
| Prediction ledger | `ledger/predictions/*.csv` in git | Permanent, timestamped |
| Model reports | `pipeline/reports/` in git | Permanent |

## Failure handling

- Any failing source: other sources still update, last good data is kept, the run fails → GitHub emails the owner.
- Validation failure: models and publish are skipped (bad data is never published).
- FBref failure: logged only (soft source; age/nationality may go stale).
- DB > 350 MB: publish rolls back and fails.

## Security model (Supabase advisor notes)

- Tables live in `core` (not exposed by the Data API). Views in `public` run with the caller's privileges; API roles can read only the football-data tables. `core.app_secrets`, `core.ask_usage` and `core.ask_log` are not readable by any API role.
- The advisor warns that `anon` can call four SECURITY DEFINER functions. This is intentional: `scout_similar` (read-only search) and `ask_execute` (runs as the read-only `ask_reader` role with a 5 s timeout and 200-row cap) power public features; `ask_consume_quota` and `ask_log_insert` refuse to run without the server token.
