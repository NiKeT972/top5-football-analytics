/**
 * Runs the 30-question evaluation against the live database + configured LLM and writes
 * eval/report.md. Skipped unless ASK_EVAL=1 (needs SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and an LLM key).
 * Run: ASK_EVAL=1 npx vitest run --config vitest.eval.config.ts
 */
import { writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ask } from "@/lib/ask/agent";
import { db } from "@/lib/supabase";
import { CASES, isCorrect } from "./questions";

const run = process.env.ASK_EVAL === "1";
const PAUSE_MS = Number(process.env.ASK_EVAL_PAUSE_MS ?? 4000); // stay inside free-tier rate limits

async function execute(sql: string) {
  const { data, error } = await db().rpc("ask_execute", { query: sql, max_rows: 200 }, { get: true });
  return error ? { error: error.message } : { rows: (data as Record<string, unknown>[]) ?? [] };
}

describe.skipIf(!run)("Ask agent evaluation", () => {
  it("answers the evaluation set", async () => {
    const lines = ["| # | question | correct | note |", "|---|---|---|---|"];
    let correct = 0;
    for (const c of CASES) {
      const ref = await execute(c.ref);
      let ok = false;
      let note = "";
      try {
        const res = await ask(c.q, execute);
        ok = "rows" in ref && ref.rows !== undefined && isCorrect(ref.rows, res.rows);
        note = res.error ?? (res.sql ? "" : "no SQL");
      } catch (e) {
        note = e instanceof Error ? e.message.slice(0, 80) : "error";
      }
      if (ok) correct++;
      lines.push(`| ${c.id} | ${c.q} | ${ok ? "yes" : "no"} | ${note.replace(/\|/g, "/")} |`);
      await new Promise((r) => setTimeout(r, PAUSE_MS));
    }
    const header = `# Ask agent evaluation\n\nModel: ${process.env.LLM_PROVIDER ?? "google"} / ${process.env.LLM_MODEL ?? "default"} · run ${new Date().toISOString()}\n\n**Accuracy: ${correct}/${CASES.length} (${((100 * correct) / CASES.length).toFixed(0)}%)**\n\n`;
    writeFileSync(new URL("./report.md", import.meta.url), header + lines.join("\n") + "\n");
    expect(correct).toBeGreaterThan(0);
  }, 30 * 60_000);
});
