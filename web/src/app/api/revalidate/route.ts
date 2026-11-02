import { revalidateTag } from "next/cache";
import { DATA_TAG } from "@/lib/data";

/** Called by the daily pipeline after publishing: POST with `Authorization: Bearer <REVALIDATE_SECRET>`. */
export async function POST(request: Request) {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ revalidated: false, error: "unauthorised" }, { status: 401 });
  }
  revalidateTag(DATA_TAG, "max");
  return Response.json({ revalidated: true, tag: DATA_TAG, now: Date.now() });
}
