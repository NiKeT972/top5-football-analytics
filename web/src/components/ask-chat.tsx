"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Result {
  question: string;
  answer?: string;
  sql?: string | null;
  rows?: Record<string, unknown>[];
  chart?: { type: "table" | "bar" | "line"; x?: string; y?: string } | null;
  error?: string;
}

const SUGGESTIONS = [
  "Which Bundesliga forward has the best npxG per 90 this season, minimum 900 minutes?",
  "Which Premier League team has overperformed its expected points the most?",
  "Penalty conversion rate by league",
  "Most key passes per 90 among Ligue 1 midfielders under 23",
];

function ResultChart({ r }: { r: Result }) {
  const { chart, rows = [] } = r;
  if (!chart || chart.type === "table" || !chart.x || !chart.y || rows.length < 2 || typeof rows[0][chart.y] !== "number" && Number.isNaN(Number(rows[0][chart.y]))) return null;
  const data = rows.slice(0, 25).map((row) => ({ ...row, [chart.y!]: Number(row[chart.y!]) }));
  const style = { contentStyle: { background: "var(--surface-1)", border: "1px solid var(--border)", fontSize: 12 } };
  return (
    <div className="mt-3 h-64">
      <ResponsiveContainer>
        {chart.type === "line" ? (
          <LineChart data={data}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey={chart.x} fontSize={11} stroke="var(--text-muted)" /><YAxis fontSize={11} stroke="var(--text-muted)" /><Tooltip {...style} /><Line dataKey={chart.y} stroke="var(--s1)" strokeWidth={2} dot={false} /></LineChart>
        ) : (
          <BarChart data={data} layout="vertical" margin={{ left: 24 }}><CartesianGrid stroke="var(--border)" horizontal={false} /><XAxis type="number" fontSize={11} stroke="var(--text-muted)" /><YAxis type="category" dataKey={chart.x} width={140} fontSize={11} stroke="var(--text-muted)" /><Tooltip {...style} /><Bar dataKey={chart.y} fill="var(--s1)" radius={[0, 4, 4, 0]} /></BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="text-sm text-fg-3">No rows.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="mt-3 max-h-80 overflow-auto rounded-md border border-border">
      <table className="w-full text-xs tabular">
        <thead className="sticky top-0 bg-surface-2"><tr>{cols.map((c) => <th key={c} className="px-2 py-1.5 text-left font-medium text-fg-2">{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-border/60">{cols.map((c) => <td key={c} className="px-2 py-1">{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export function AskChat() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Result[]>([]);

  async function submit(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true);
    setQuestion("");
    try {
      const res = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: q }) });
      const data = await res.json();
      setHistory((h) => [{ question: q, ...data }, ...h]);
    } catch {
      setHistory((h) => [{ question: q, error: "Network error." }, ...h]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); submit(question); }} className="flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} placeholder="Ask about players, teams, xG, predictions…" aria-label="Question" className="flex-1 rounded-md border border-border bg-surface-1 px-3 py-2 text-fg" />
        <button disabled={busy} className="rounded-md bg-[var(--btn)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{busy ? "Thinking…" : "Ask"}</button>
      </form>
      {history.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => <button key={s} onClick={() => submit(s)} className="rounded-full border border-border bg-surface-1 px-3 py-1 text-left text-xs text-fg-2 hover:text-fg">{s}</button>)}
        </div>
      )}
      {history.map((r, i) => (
        <article key={i} className="rounded-xl border border-border bg-surface-1 p-4">
          <p className="font-medium text-fg">{r.question}</p>
          {r.error && !r.answer ? <p className="mt-2 text-sm text-critical">{r.error}</p> : (
            <>
              <p className="mt-2 text-sm text-fg-2">{r.answer}</p>
              {r.sql && (
                <details className="mt-3" open>
                  <summary className="cursor-pointer text-xs font-medium text-fg-3">SQL that was run (read-only)</summary>
                  <pre className="mt-1 overflow-x-auto rounded-md bg-surface-2 p-3 text-xs"><code>{r.sql}</code></pre>
                </details>
              )}
              <ResultChart r={r} />
              {r.rows && r.sql && <ResultTable rows={r.rows} />}
            </>
          )}
        </article>
      ))}
    </div>
  );
}
