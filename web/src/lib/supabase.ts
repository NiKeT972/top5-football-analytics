import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Server-side, read-only Supabase client. It uses the publishable key, which can only
 * SELECT the documented public views and call the whitelisted RPC functions.
 */
let client: SupabaseClient | null = null;

export function isConfigured(): boolean {
  return Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_PUBLISHABLE_KEY);
}

export function db(): SupabaseClient {
  if (!isConfigured()) throw new Error("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY are not set");
  client ??= createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_PUBLISHABLE_KEY!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return client;
}
