"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { account, type AgentCreated, type Me, money, type PastSession } from "@/lib/api";
import { existingToken, signIn, signOut, signUp } from "@/lib/supabase";

const card = "flex flex-col gap-3 rounded-2xl border border-zinc-200 p-6 dark:border-zinc-800";
const input = "rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700";
const primary = "w-fit rounded-full bg-black px-5 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black";
const quiet = "w-fit text-sm text-zinc-500 underline disabled:opacity-50";

// What the shopper pastes into their Grok Bot automation, so it knows what Eden sends it.
const AUTOMATION_INSTRUCTIONS =
  "When Eden Matrix sends a shopping session, the webhook body has a `prompt` and the session's links. " +
  "Follow the prompt: get the shortlist from the Eden API, recommend the best items, and keep " +
  "/workspace/eden-matrix/sessions.md up to date so you remember my sessions.";

/** Where to go after signing in: a same-site path from ?next=, e.g. back to a confirm page. */
function nextPath(): string | null {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function Copy({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={quiet}
      onClick={() => navigator.clipboard.writeText(text).then(() => setDone(true), () => setDone(false))}
    >
      {done ? "Copied" : label}
    </button>
  );
}

/** Sign up (upgrading the guest), sign in, the demo agent card, connected agents, past sessions. */
export function AccountView() {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [sessions, setSessions] = useState<PastSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cap, setCap] = useState("200");
  const [created, setCreated] = useState<AgentCreated | null>(null);
  const [hookUrl, setHookUrl] = useState("");
  const [hookKey, setHookKey] = useState("");

  const fetchAccount = useCallback(async () => {
    const t = await existingToken();
    if (!t) return { token: null, me: null, sessions: [] as PastSession[] };
    const [m, s] = await Promise.all([account.me(t), account.sessions(t)]);
    return { token: t, me: m, sessions: s };
  }, []);

  const show = useCallback((found: { token: string | null; me: Me | null; sessions: PastSession[] }) => {
    setToken(found.token);
    setMe(found.me);
    setSessions(found.sessions);
    if (found.me?.card?.spend_cap) setCap(String(found.me.card.spend_cap));
    setLoading(false);
  }, []);

  const load = useCallback(async () => show(await fetchAccount()), [fetchAccount, show]);

  useEffect(() => {
    let stopped = false;
    fetchAccount().then(
      (found) => !stopped && show(found),
      (e) => {
        if (stopped) return;
        setError(e instanceof Error ? e.message : "Couldn't load your account.");
        setLoading(false);
      },
    );
    return () => {
      stopped = true;
    };
  }, [fetchAccount, show]);

  /** Run an action, show its outcome, and reload the account. */
  const act = async (fn: () => Promise<string | void>) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const said = await fn();
      if (said) setMessage(said);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const afterSignIn = () => {
    const next = nextPath();
    if (next) window.location.assign(next);
  };

  if (loading) {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 items-center justify-center px-6">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-black dark:border-zinc-700 dark:border-t-white" />
      </main>
    );
  }

  const signedIn = me !== null && !me.is_anonymous;
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm uppercase tracking-widest text-zinc-500">
          Eden Matrix
        </Link>
        <h1 className="text-3xl font-semibold">Your account</h1>
        {signedIn ? (
          <p className="text-zinc-600 dark:text-zinc-400">
            Signed in as {me.email}.{" "}
            <button type="button" className="underline" onClick={() => act(async () => void (await signOut()))}>
              Sign out
            </button>
          </p>
        ) : (
          <p className="text-zinc-600 dark:text-zinc-400">
            An account lets your agent remember your sessions and buy for you, only ever after you confirm here.
          </p>
        )}
      </header>

      {message && <p className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">{message}</p>}
      {error && <p className="rounded-xl bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-100">{error}</p>}

      {!signedIn && (
        <section className={card}>
          <h2 className="text-lg font-semibold">Create an account or sign in</h2>
          <p className="text-sm text-zinc-500">Sessions you started on this device as a guest come with you when you create an account.</p>
          <input className={input} type="text" placeholder="Email (or username to sign in)" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input className={input} type="password" placeholder="Password (8+ characters)" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              className={primary}
              disabled={busy || !email.includes("@") || password.length < 8}
              onClick={() =>
                act(async () => {
                  const outcome = await signUp(email, password);
                  if (outcome === "signed_in") {
                    afterSignIn();
                    return "Account created. Your guest sessions are now yours.";
                  }
                  return `Check ${email} for a confirmation link. Your account is ready once you click it.`;
                })
              }
            >
              Create account
            </button>
            <button
              type="button"
              className={quiet}
              disabled={busy || !email || !password}
              onClick={() =>
                act(async () => {
                  await signIn(email, password);
                  afterSignIn();
                  return "Signed in.";
                })
              }
            >
              I have an account: sign in
            </button>
          </div>
        </section>
      )}

      {signedIn && (
        <section className={card}>
          <h2 className="text-lg font-semibold">Agent card</h2>
          {me.card ? (
            <p>
              {me.card.label} •••• {me.card.last4} · up to {money(me.card.spend_cap, me.card.currency)} a purchase
            </p>
          ) : (
            <p className="text-sm text-zinc-500">No card yet. Add one and your agent can ask to buy for you.</p>
          )}
          <label className="flex items-center gap-2 text-sm">
            Limit per purchase (£)
            <input className={`${input} w-28`} type="number" min={1} max={5000} value={cap} onChange={(e) => setCap(e.target.value)} />
          </label>
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              className={primary}
              disabled={busy || !(Number(cap) > 0)}
              onClick={() =>
                act(async () => {
                  await account.linkCard(token!, Number(cap));
                  return me.card ? "Limit updated." : "Demo agent card added.";
                })
              }
            >
              {me.card ? "Update limit" : "Add demo agent card"}
            </button>
            {me.card && (
              <button type="button" className={quiet} disabled={busy} onClick={() => act(async () => void (await account.unlinkCard(token!)))}>
                Remove card
              </button>
            )}
          </div>
          <p className="text-xs text-zinc-500">
            Demo card: nothing real is issued or charged. Your agent never sees card details, only that a card is
            ready and its last four digits, and nothing is bought until you confirm on Eden.
          </p>
        </section>
      )}

      {signedIn && (
        <section className={card}>
          <h2 className="text-lg font-semibold">Connect Grok Bot</h2>
          <p className="text-sm text-zinc-500">
            Gives your Grok Bot the Eden Matrix tools over MCP: it can list your past sessions, read any
            session&apos;s shortlist, start new ones, and ask to buy with your agent card.
          </p>
          {created ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm">
                In Grok Bot, open the MCP servers settings, add a server by JSON and paste this. The token is shown
                only once.
              </p>
              <pre className="overflow-x-auto rounded-lg bg-zinc-100 p-3 text-xs dark:bg-zinc-900">
                {JSON.stringify(created.mcp_config, null, 2)}
              </pre>
              <Copy text={JSON.stringify(created.mcp_config, null, 2)} label="Copy the JSON" />
              <p className="text-sm text-zinc-500">
                Then ask Grok Bot: &ldquo;What have I been shopping for on Eden?&rdquo;
              </p>
            </div>
          ) : (
            <button
              type="button"
              className={primary}
              disabled={busy}
              onClick={() =>
                act(async () => {
                  setCreated(await account.connectAgent(token!, "Grok Bot"));
                })
              }
            >
              Connect Grok Bot
            </button>
          )}
          {me.agents.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm">
              {me.agents.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3">
                  <span>
                    {a.name} · token …{a.token_hint} ·{" "}
                    {a.last_used_at ? `last used ${new Date(a.last_used_at).toLocaleString()}` : "not used yet"}
                  </span>
                  <button type="button" className={quiet} disabled={busy} onClick={() => act(async () => void (await account.disconnectAgent(token!, a.id)))}>
                    Disconnect
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {signedIn && (
        <section className={card}>
          <h2 className="text-lg font-semibold">Send sessions straight to Grok Bot</h2>
          {me.grok_bot_webhook ? (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span>
                Connected to {me.grok_bot_webhook.host}
                {me.grok_bot_webhook.last_sent_at
                  ? ` · last sent ${new Date(me.grok_bot_webhook.last_sent_at).toLocaleString()}`
                  : ""}
                . Session pages now have a Send to Grok Bot button.
              </span>
              <button type="button" className={quiet} disabled={busy} onClick={() => act(async () => void (await account.removeWebhook(token!)))}>
                Remove
              </button>
            </div>
          ) : (
            <>
              <ol className="list-decimal pl-5 text-sm text-zinc-600 dark:text-zinc-400">
                <li>In Grok Bot, create an automation and pick the trigger &ldquo;When a webhook fires&rdquo;.</li>
                <li>
                  Give it these instructions: <Copy text={AUTOMATION_INSTRUCTIONS} label="copy instructions" />
                </li>
                <li>Paste its webhook URL and key here.</li>
              </ol>
              <input className={input} placeholder="Webhook URL (https://…)" value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} />
              <input className={input} type="password" placeholder="Webhook key" value={hookKey} onChange={(e) => setHookKey(e.target.value)} />
              <button
                type="button"
                className={primary}
                disabled={busy || !hookUrl.startsWith("https://") || hookKey.length < 8}
                onClick={() =>
                  act(async () => {
                    await account.setWebhook(token!, hookUrl.trim(), hookKey.trim());
                    setHookKey("");
                    return "Saved. Session pages now send straight to your Grok Bot.";
                  })
                }
              >
                Save automation
              </button>
            </>
          )}
        </section>
      )}

      {sessions.length > 0 && (
        <section className={card}>
          <h2 className="text-lg font-semibold">Your sessions</h2>
          <ul className="flex flex-col gap-2 text-sm">
            {sessions.map((s) => (
              <li key={s.code} className="flex flex-wrap items-baseline justify-between gap-2">
                <Link href={`/s/${s.code}`} className="font-medium hover:underline">
                  {s.collection || s.store}
                </Link>
                <span className="text-zinc-500">
                  {s.store} · {s.product_count} products · {s.status} · {new Date(s.created_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
