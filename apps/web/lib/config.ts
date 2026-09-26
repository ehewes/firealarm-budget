// Public settings, compiled into the bundle at build time (NEXT_PUBLIC_* only, CLAUDE.md rule 6).

// The Eden API. Production: https://go.edenmatrix.xyz/v1 (same host). Local: http://localhost:8000/v1.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "/v1").replace(/\/$/, "");

export const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
// The publishable (anon) key. Never a secret key: this value ships to every browser.
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

// Grok Bot, xAI's desktop app for macOS, Windows and Linux. Its links open the app but can't
// carry a prompt: the routes it registers are /v1/open, /v1/agent?id=, /v1/bot-template?id= and
// a few settings pages (Info.plist and app.asar, v0.59.1). So the session page copies the prompt
// as it opens the app, and the shopper pastes it in.
export const GROK_BOT_APP_URL = "grokbot://app/v1/open";
export const GROK_BOT_DOWNLOAD_URL = "https://x.ai/bot";
