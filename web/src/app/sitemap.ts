import type { MetadataRoute } from "next";
import { LEAGUES } from "@/lib/leagues";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return [
    { url: base, changeFrequency: "daily", priority: 1 },
    ...LEAGUES.map((l) => ({ url: `${base}/league/${l.slug}`, changeFrequency: "daily" as const, priority: 0.8 })),
    ...["scout", "ask", "model", "about"].map((p) => ({ url: `${base}/${p}`, changeFrequency: "weekly" as const, priority: 0.6 })),
  ];
}
