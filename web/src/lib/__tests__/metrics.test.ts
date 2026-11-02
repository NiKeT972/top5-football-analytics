import { describe, expect, it } from "vitest";
import { cumulativeXg, mean, outcomeIndex, rolling, rps } from "../metrics";
import { num, pct, seasonLabel, signed } from "../format";

describe("rolling", () => {
  it("averages a trailing window and skips nulls", () => {
    expect(rolling([1, 2, null, 4], 2)).toEqual([1, 1.5, 2, 4]);
  });
});

describe("cumulativeXg", () => {
  it("accumulates per side and marks goals", () => {
    const pts = cumulativeXg([
      { minute: 10, xg: 0.5, side: "h", is_goal: true },
      { minute: 5, xg: 0.1, side: "a", is_goal: false },
    ]);
    expect(pts[1]).toEqual({ minute: 5, home: 0, away: 0.1, goal: undefined });
    expect(pts[2]).toMatchObject({ minute: 10, home: 0.5, goal: "h" });
    expect(pts.at(-1)).toMatchObject({ minute: 90, home: 0.5, away: 0.1 });
  });
});

describe("scoring", () => {
  it("rps is 0 for a perfect forecast and 1 for the worst", () => {
    expect(rps([1, 0, 0], 0)).toBe(0);
    expect(rps([1, 0, 0], 2)).toBe(1);
  });
  it("outcome index", () => {
    expect([outcomeIndex(2, 1), outcomeIndex(1, 1), outcomeIndex(0, 3)]).toEqual([0, 1, 2]);
  });
  it("mean ignores nulls", () => expect(mean([1, null, 3])).toBe(2));
});

describe("format", () => {
  it("formats numbers", () => {
    expect(pct(0.456)).toBe("46%");
    expect(num(null)).toBe("–");
    expect(signed(-1.25)).toBe("−1.3");
    expect(seasonLabel("2627")).toBe("2026/27");
  });
});
