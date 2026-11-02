import { ask } from "@/lib/ask/agent";
import { llmConfigured } from "@/lib/ask/provider";
import { SITE } from "@/lib/config";
import { db, isConfigured } from "@/lib/supabase";

const WINDOW_MS = 60_000;
const PER_IP_PER_WINDOW = 6;
const hits = new Map<string, number[]>();

/** Best-effort per-instance rate limit; the global daily cap lives in Postgres. */
function rateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > PER_IP_PER_WINDOW;
}

async function execute(sql: string) {
  const { data, error } = await db().rpc("ask_execute", { query: sql, max_rows: SITE.ask.maxRows }, { get: true });
  if (error) return { error: error.message };
  return { rows: (data as Record<string, unknown>[]) ?? [] };
}

export async function POST(request: Request) {
  const started = Date.now();
  const body = (await request.json().catch(() => null)) as { question?: unknown } | null;
  const question = typeof body?.question === "string" ? body.question.trim() : "";
  if (!question || question.length > SITE.ask.maxQuestionChars) {
    return Response.json({ error: `Ask a question of 1–${SITE.ask.maxQuestionChars} characters.` }, { status: 400 });
  }
  if (!isConfigured() || !llmConfigured() || !process.env.ASK_SERVER_TOKEN) {
    return Response.json({ error: "Ask is not configured on this deployment." }, { status: 503 });
  }
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (rateLimited(ip)) return Response.json({ error: "Too many questions, please wait a minute." }, { status: 429 });

  const { data: remaining, error: quotaError } = await db().rpc("ask_consume_quota", { token: process.env.ASK_SERVER_TOKEN, daily_cap: SITE.ask.dailyCap });
  if (quotaError) return Response.json({ error: "Ask is temporarily unavailable." }, { status: 503 });
  if ((remaining as number) < 0) return Response.json({ error: "Today's free question budget is used up. Please come back tomorrow." }, { status: 429 });

  try {
    const result = await ask(question, execute);
    await db().rpc("ask_log_insert", {
      token: process.env.ASK_SERVER_TOKEN, p_question: question, p_sql: result.sql, p_ok: !result.error,
      p_n_rows: result.rows.length, p_latency_ms: Date.now() - started, p_error: result.error ?? null,
    });
    return Response.json(result);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    console.error("[ask]", message);
    return Response.json({ error: "The language model is unavailable right now. Please try again later." }, { status: 502 });
  }
}
