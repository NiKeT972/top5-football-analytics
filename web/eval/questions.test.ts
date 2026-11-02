import { describe, expect, it } from "vitest";
import { guardSql } from "@/lib/ask/guard";
import { EXAMPLES } from "@/lib/ask/context";
import { CASES, isCorrect } from "./questions";

describe("eval set", () => {
  it("has 30 unique questions whose reference SQL passes the guard", () => {
    expect(CASES).toHaveLength(30);
    expect(new Set(CASES.map((c) => c.q)).size).toBe(30);
    for (const c of CASES) expect(guardSql(c.ref), c.ref).toMatchObject({ ok: true });
  });
  it("does not overlap with the few-shot examples", () => {
    const ex = new Set(EXAMPLES.map((e) => e.q.toLowerCase()));
    expect(CASES.filter((c) => ex.has(c.q.toLowerCase()))).toEqual([]);
  });
  it("scores result sets regardless of column names and order", () => {
    expect(isCorrect([{ player: "Harry Kane" }], [{ name: "Harry Kane", npxg: 0.71 }])).toBe(true);
    expect(isCorrect([{ count: 42 }], [{ n: "42" }])).toBe(true);
    expect(isCorrect([{ player: "Kane" }], [{ player: "Haaland" }])).toBe(false);
  });
});
