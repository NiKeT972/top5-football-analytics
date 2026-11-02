/**
 * SQL guardrail for the Ask agent (first line of defence; the database enforces the same
 * rules again: read-only role, whitelisted views, 5 s timeout, 200-row cap).
 *
 * Accepts exactly one read-only SELECT (CTEs and UNIONs allowed) that only reads the
 * documented public views and calls no dangerous functions.
 */
import { astVisitor, parse, type Statement } from "pgsql-ast-parser";

export const ALLOWED_VIEWS = new Set([
  "leagues", "teams", "matches", "team_matches", "league_table", "team_elo", "shots", "player_seasons",
  "player_matches", "player_percentiles", "similar_players", "latest_predictions", "fixtures",
  "prediction_track_record", "backtest_results",
]);

const FORBIDDEN_FUNCTION = /^(pg_|lo_|dblink|set_config|current_setting|query_to_xml|xpath|txid_|nextval|setval|ask_|scout_)/i;
const FORBIDDEN_WORDS = /\b(insert|update|delete|merge|drop|alter|create|grant|revoke|truncate|copy|call|do|set|reset|listen|notify|vacuum|analyze|refresh|lock|comment|prepare|execute)\b/i;
const SELECT_TYPES = new Set(["select", "union", "union all", "with", "with recursive", "values"]);

export type GuardResult = { ok: true; sql: string; parsed: boolean } | { ok: false; reason: string };

function stripLiterals(sql: string): string {
  return sql.replace(/'(?:[^']|'')*'/g, "''").replace(/--[^\n]*/g, " ").replace(/\/\*[\s\S]*?\*\//g, " ");
}

export function guardSql(raw: string): GuardResult {
  const sql = raw.trim().replace(/;+\s*$/, "").trim();
  if (!sql) return { ok: false, reason: "empty query" };
  if (sql.length > 4000) return { ok: false, reason: "query too long" };
  const bare = stripLiterals(sql);
  if (bare.includes(";")) return { ok: false, reason: "only one statement is allowed" };
  if (FORBIDDEN_WORDS.test(bare)) return { ok: false, reason: "only read-only SELECT queries are allowed" };

  let statements: Statement[];
  try {
    statements = parse(sql);
  } catch {
    // The parser does not know every Postgres construct. Fall back to the conservative
    // lexical checks above; the database role still only permits SELECT on public views.
    if (!/^\s*(select|with)\b/i.test(bare)) return { ok: false, reason: "query must start with SELECT or WITH" };
    const refs = [...bare.matchAll(/\b(?:from|join)\s+([a-z_][a-z0-9_.]*)/gi)].map((m) => m[1].toLowerCase().replace(/^public\./, ""));
    const bad = refs.filter((r) => r.includes(".") || (!ALLOWED_VIEWS.has(r) && !new RegExp(`\\b${r}\\s+as\\s*\\(`, "i").test(bare)));
    if (bad.length) return { ok: false, reason: `unknown or forbidden relation: ${bad[0]}` };
    return { ok: true, sql, parsed: false };
  }
  if (statements.length !== 1) return { ok: false, reason: "only one statement is allowed" };
  const st = statements[0];
  if (!SELECT_TYPES.has(st.type)) return { ok: false, reason: `statement type ${st.type} is not allowed` };

  const cteNames = new Set<string>();
  const tables: string[] = [];
  const problems: string[] = [];
  const visitor = astVisitor((m) => ({
    with: (w) => {
      for (const b of w.bind) cteNames.add(b.alias.name.toLowerCase());
      m.super().with(w);
    },
    tableRef: (t) => {
      if (t.schema && t.schema.toLowerCase() !== "public") problems.push(`schema ${t.schema} is not allowed`);
      tables.push(t.name.toLowerCase());
    },
    call: (c) => {
      if (c.function.schema || FORBIDDEN_FUNCTION.test(c.function.name)) problems.push(`function ${c.function.name} is not allowed`);
      m.super().call(c);
    },
    insert: () => problems.push("INSERT is not allowed"),
    update: () => problems.push("UPDATE is not allowed"),
    delete: () => problems.push("DELETE is not allowed"),
  }));
  visitor.statement(st);
  for (const t of tables) if (!ALLOWED_VIEWS.has(t) && !cteNames.has(t)) problems.push(`unknown relation ${t}`);
  if (problems.length) return { ok: false, reason: problems[0] };
  return { ok: true, sql, parsed: true };
}
