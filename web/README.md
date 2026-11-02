# PitchIQ web

Next.js 16 (App Router, Cache Components) + TypeScript + Tailwind v4 + Recharts.
Reads the read-only `public` views in Supabase; every reader is a cached function tagged
`pitchiq-data`, refreshed by the daily pipeline via `POST /api/revalidate`.

```bash
cp .env.example .env.local   # fill in Supabase URL + publishable key
npm install
npm run dev                  # http://localhost:3000
npm test                     # data-layer + SQL-guard unit tests
npm run lint && npm run typecheck
```

Ask evaluation (needs DB + LLM key): `ASK_EVAL=1 npx vitest run --config vitest.eval.config.ts` → `eval/report.md`.
