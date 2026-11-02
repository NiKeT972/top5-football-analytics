import { describe, expect, it } from "vitest";
import { retrieveExamples, EXAMPLES } from "../ask/context";
import { guardSql } from "../ask/guard";

describe("guardSql", () => {
  it("accepts every worked example", () => {
    for (const e of EXAMPLES) expect(guardSql(e.sql), e.sql).toMatchObject({ ok: true });
  });
  it("accepts CTEs and strips a trailing semicolon", () => {
    const r = guardSql("with t as (select team, points from league_table) select * from t order by points desc;");
    expect(r).toMatchObject({ ok: true, sql: expect.not.stringContaining(";") });
  });
  it.each([
    ["delete from matches", "only read-only"],
    ["select 1; drop table matches", "one statement"],
    ["select * from core.matches", "schema"],
    ["select * from pg_catalog.pg_roles", "not allowed"],
    ["select pg_sleep(10)", "pg_sleep"],
    ["select * from secrets", "unknown relation"],
    ["with x as (insert into teams values (1) returning *) select * from x", "read-only"],
    ["select set_config('role', 'postgres', false)", "set_config"],
  ])("rejects %s", (sql, reason) => {
    const r = guardSql(sql);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toContain(reason);
  });
  it("does not trip on keywords inside string literals", () => {
    expect(guardSql("select player from player_seasons where player ilike '%Delete%'")).toMatchObject({ ok: true });
  });
});

describe("retrieveExamples", () => {
  it("returns the most relevant example first", () => {
    expect(retrieveExamples("best xA per 90 La Liga winger")[0].sql).toContain("xa_per90");
  });
});
