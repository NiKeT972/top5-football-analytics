/** Site-level tunables (kept here, not scattered as magic numbers). */
export const SITE = {
  fixtureDays: 7,
  edgeMin: 0.04,
  maxEdges: 8,
  rollingWindow: 10,
  scoutDefaultMinMinutes: 900,
  scoutMaxAgeOptions: [21, 23, 25, 28, 32],
  radarMetrics: ["npxg", "xa", "shots", "key_passes", "xg_chain", "xg_buildup", "np_goals", "assists", "npxg_per_shot"],
  scoreGridMaxGoals: 5,
  ask: { dailyCap: Number(process.env.ASK_DAILY_CAP ?? 300), maxRows: 200, maxQuestionChars: 300 },
} as const;

export const METRIC_LABEL: Record<string, string> = {
  npxg: "npxG", xa: "xA", shots: "Shots", key_passes: "Key passes", xg_chain: "xGChain", xg_buildup: "xGBuildup",
  np_goals: "NP goals", assists: "Assists", npxg_per_shot: "npxG/shot", xg: "xG", goals: "Goals",
};
