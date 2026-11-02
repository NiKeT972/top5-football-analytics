/**
 * Text-to-SQL agent: question -> SQL (structured output) -> guard -> read-only execution ->
 * short natural-language answer. At most one self-correction round on a SQL error, so a
 * question costs at most three LLM calls.
 */
import { generateText, Output } from "ai";
import { z } from "zod";
import { GLOSSARY, retrieveExamples, SCHEMA_DOC } from "./context";
import { guardSql } from "./guard";
import { model } from "./provider";

export const SqlPlan = z.object({
  sql: z.string().describe("One read-only Postgres SELECT over the documented views. No semicolon."),
  chart: z.object({
    type: z.enum(["table", "bar", "line"]).describe("bar for rankings/comparisons, line for time series, table otherwise"),
    x: z.string().optional().describe("column for the x axis / category"),
    y: z.string().optional().describe("numeric column for the y axis"),
  }),
  unanswerable: z.string().optional().describe("Set only if the data cannot answer the question; explain why."),
});
export type SqlPlan = z.infer<typeof SqlPlan>;

export type Executor = (sql: string) => Promise<{ rows: Record<string, unknown>[] } | { error: string }>;

export interface AskResult {
  answer: string;
  sql: string | null;
  rows: Record<string, unknown>[];
  chart: SqlPlan["chart"] | null;
  error?: string;
}

function system(question: string): string {
  const examples = retrieveExamples(question).map((e) => `Q: ${e.q}\nSQL: ${e.sql}`).join("\n\n");
  return [
    "You translate football analytics questions into ONE read-only PostgreSQL SELECT over these views.",
    "Never invent columns. Use ILIKE for name matching. Round decimals to 2-3 places. Always add a LIMIT (<= 50) for rankings.",
    "If the question is not about the data below (or asks to modify anything), set `unanswerable`.",
    SCHEMA_DOC,
    GLOSSARY,
    `Examples:\n${examples}`,
  ].join("\n\n");
}

export async function planSql(question: string, previous?: { sql: string; error: string }): Promise<SqlPlan> {
  const prompt = previous
    ? `${question}\n\nYour previous SQL failed:\n${previous.sql}\nError: ${previous.error}\nReturn a corrected query.`
    : question;
  const { output } = await generateText({ model: model(), system: system(question), prompt, output: Output.object({ schema: SqlPlan }), temperature: 0 });
  return output;
}

async function summarise(question: string, sql: string, rows: Record<string, unknown>[]): Promise<string> {
  const { text } = await generateText({
    model: model(),
    temperature: 0,
    system: "Answer the football question in 1-3 sentences using ONLY the query result. Mention units (per 90, xG). If the result is empty, say so. No speculation.",
    prompt: `Question: ${question}\nSQL: ${sql}\nResult (first rows, JSON): ${JSON.stringify(rows.slice(0, 20))}`,
  });
  return text.trim();
}

export async function ask(question: string, execute: Executor): Promise<AskResult> {
  let plan = await planSql(question);
  if (plan.unanswerable) return { answer: plan.unanswerable, sql: null, rows: [], chart: null };
  for (let attempt = 0; attempt < 2; attempt++) {
    const g = guardSql(plan.sql);
    const res = g.ok ? await execute(g.sql) : { error: `rejected by guard: ${g.reason}` };
    if ("rows" in res) {
      return { answer: await summarise(question, plan.sql, res.rows), sql: plan.sql, rows: res.rows, chart: plan.chart };
    }
    if (attempt === 1) return { answer: "Sorry, I could not build a valid query for that question.", sql: plan.sql, rows: [], chart: null, error: res.error };
    plan = await planSql(question, { sql: plan.sql, error: res.error });
    if (plan.unanswerable) return { answer: plan.unanswerable, sql: null, rows: [], chart: null };
  }
  return { answer: "Sorry, something went wrong.", sql: null, rows: [], chart: null };
}
