import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./config";

let client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Sign-in isn't configured for this build (NEXT_PUBLIC_SUPABASE_* are missing).");
  }
  client ??= createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return client;
}

/**
 * A token for the Eden API: the visitor's existing session, or a new anonymous one.
 * Guests sign in anonymously on first visit (CLAUDE.md), so one code path serves both.
 */
export async function accessToken(): Promise<string> {
  const sb = supabase();
  const { data } = await sb.auth.getSession();
  if (data.session) return data.session.access_token;

  const { data: anon, error } = await sb.auth.signInAnonymously();
  if (error || !anon.session) {
    if (error?.code === "anonymous_provider_disabled") {
      throw new Error(
        "Guest sign-in isn't switched on yet. In Supabase, allow anonymous sign-ins, then try again.",
      );
    }
    throw new Error(error?.message ?? "Couldn't sign you in. Please try again.");
  }
  return anon.session.access_token;
}
