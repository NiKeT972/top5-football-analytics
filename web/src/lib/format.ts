/** Display formatting helpers (all times shown in IST, the site's home timezone). */
export const TZ = "Asia/Kolkata";

export function pct(p: number | null | undefined, digits = 0): string {
  return p == null || Number.isNaN(p) ? "–" : `${(p * 100).toFixed(digits)}%`;
}

export function num(x: number | null | undefined, digits = 2): string {
  return x == null || Number.isNaN(Number(x)) ? "–" : Number(x).toFixed(digits);
}

export function signed(x: number | null | undefined, digits = 1): string {
  if (x == null || Number.isNaN(Number(x))) return "–";
  const v = Number(x);
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}`;
}

export function kickoff(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: TZ, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso));
}

export function dateOnly(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}

export function seasonLabel(seasonId: string): string {
  return `${2000 + Number(seasonId.slice(0, 2))}/${seasonId.slice(2)}`;
}

export const POSITION_LABEL: Record<string, string> = {
  FW: "Forward", AMW: "Attacking mid / winger", CM: "Central midfielder", DEF: "Defender", GK: "Goalkeeper",
};
