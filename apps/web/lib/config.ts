// Public settings, compiled into the bundle at build time (NEXT_PUBLIC_* only, CLAUDE.md rule 6).

// The Eden API. Production: https://go.edenmatrix.xyz/v1 (same host). Local: http://localhost:8000/v1.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "/v1").replace(/\/$/, "");

export const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
// The publishable (anon) key. Never a secret key: this value ships to every browser.
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
