import { createClient, type SupabaseClient, type User } from "@supabase/supabase-js";

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

/** The visitor's token if they already have a session. Unlike accessToken, never creates a guest. */
export async function existingToken(): Promise<string | null> {
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function currentUser(): Promise<User | null> {
  const { data } = await supabase().auth.getSession();
  return data.session?.user ?? null;
}

/**
 * Create an account. A guest is upgraded in place (CLAUDE.md), so the sessions they started stay
 * theirs. When the project confirms emails, the account is complete once they click the link.
 */
export async function signUp(email: string, password: string): Promise<"signed_in" | "check_email"> {
  const sb = supabase();
  await accessToken(); // a guest session to upgrade, if the visitor has none yet
  const { data, error } = await sb.auth.updateUser(
    { email, password },
    { emailRedirectTo: `${window.location.origin}/dashboard` },
  );
  if (error) throw new Error(error.message);
  if (data.user && !data.user.is_anonymous) {
    await sb.auth.refreshSession(); // a token that no longer says is_anonymous
    return "signed_in";
  }
  return "check_email";
}

export async function signIn(email: string, password: string): Promise<void> {
  const { error } = await supabase().auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);
}

export async function signOut(): Promise<void> {
  await supabase().auth.signOut();
}
