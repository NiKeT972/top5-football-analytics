"use client";

/**
 * Charts are loaded lazily on the client so Recharts never blocks first paint or
 * hydration of the tables (big Total Blocking Time win on mobile).
 */
import dynamic from "next/dynamic";

const box = (h: string) => function Placeholder() {
  return <div className={`${h} w-full animate-pulse rounded-lg bg-surface-2`} aria-hidden />;
};

export const EloChart = dynamic(() => import("./client").then((m) => m.EloChart), { ssr: false, loading: box("h-80") });
export const XgScatter = dynamic(() => import("./client").then((m) => m.XgScatter), { ssr: false, loading: box("h-80") });
export const XgTimeline = dynamic(() => import("./client").then((m) => m.XgTimeline), { ssr: false, loading: box("h-64") });
export const MultiLine = dynamic(() => import("./client").then((m) => m.MultiLine), { ssr: false, loading: box("h-64") });
export const PercentileRadar = dynamic(() => import("./client").then((m) => m.PercentileRadar), { ssr: false, loading: box("h-80") });
export const CalibrationChart = dynamic(() => import("./client").then((m) => m.CalibrationChart), { ssr: false, loading: box("h-72") });
