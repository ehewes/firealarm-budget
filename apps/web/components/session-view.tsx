"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { api, type Product, productsUrl, type Session, type TreeNode } from "@/lib/api";
import { GROK_BOT_APP_URL, GROK_BOT_DOWNLOAD_URL } from "@/lib/config";

const STATUS: Record<Session["status"], string> = {
  pending: "Queued…",
  crawling: "Reading the store page…",
  classifying: "Sorting products into categories…",
  ready: "Ready",
  failed: "We couldn't read that page",
};

type Desktop = "mac" | "windows" | "linux" | null;

/** The desktop Grok Bot runs on, if this is one. iPads report themselves as Macs, but have touch. */
function desktop(): Desktop {
  const ua = navigator.userAgent;
  if (/Macintosh/.test(ua)) return navigator.maxTouchPoints > 1 ? null : "mac";
  if (/Windows/.test(ua)) return "windows";
  if (/Linux/.test(ua) && !/Android/.test(ua)) return "linux";
  return null;
}

const unchanging = () => () => {};

/** The scrape's reason for failing, as a sentence a shopper can act on. */
function failure(reason: string | null): string {
  if (!reason) return "Try again in a minute, or try another page from the same store.";
  if (reason === "budget_exhausted") return "This month's scraping budget is spent. Try again next month.";
  if (reason.includes("bot check")) return "The store blocked us with a bot check. Try again in a minute.";
  if (reason.includes("no products")) return "We found no products on that page. Try a category or search results page.";
  return reason.charAt(0).toUpperCase() + reason.slice(1) + ".";
}

function money(amount: number | null, currency: string | null): string {
  if (amount === null) return "";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "USD" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

/** The session page: live status and category tree while the scrape runs, then the handoff to Grok. */
export function SessionView({ code }: { code: string }) {
  const [session, setSession] = useState<Session | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [grokUrl, setGrokUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Read after hydration: the server can't know the visitor's platform.
  const platform = useSyncExternalStore(unchanging, desktop, () => null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Polling rather than a stream: the tunnel in front of the API buffers server-sent events.
    const tick = async () => {
      try {
        const current = await api.session(code);
        if (stopped) return;
        setSession(current);
        if (current.product_count > 0) {
          const t = await api.tree(code);
          if (!stopped) setTree(t.tree);
        }
        if (current.status === "ready") {
          const [p, g] = await Promise.all([api.products(code), api.grok(code)]);
          if (!stopped) {
            setProducts(p.items);
            setTotal(p.total_matching);
            setGrokUrl(g.grok_url);
            setPrompt(g.prompt);
          }
          return;
        }
        if (current.status === "failed") return;
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : "Something went wrong.");
        return;
      }
      timer = setTimeout(tick, 2000);
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [code]);

  if (error) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-2xl font-semibold">{error}</h1>
        <Link href="/" className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white dark:bg-white dark:text-black">
          Start again
        </Link>
      </main>
    );
  }

  const ready = session?.status === "ready";
  const button = "inline-flex w-fit items-center gap-2 rounded-full px-6 py-3 text-base font-medium";
  const primary = "bg-black text-white dark:bg-white dark:text-black";
  const secondary = "border border-zinc-300 dark:border-zinc-700";
  const waiting = "pointer-events-none bg-zinc-200 text-zinc-500 dark:bg-zinc-800";

  // The link itself opens the app, so the browser sees the click; the copy starts in the same click.
  const copyPrompt = () => {
    if (prompt) navigator.clipboard.writeText(prompt).then(() => setCopied(true), () => setCopied(false));
  };

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
      <header className="flex flex-col gap-2">
        <p className="text-sm uppercase tracking-widest text-zinc-500">Eden Matrix · {code}</p>
        <h1 className="text-3xl font-semibold">{session?.collection || session?.store || "Loading…"}</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          {session ? `${session.store} · ${session.product_count} products · ${STATUS[session.status]}` : "Loading session…"}
        </p>
        {session?.status === "failed" && (
          <p className="text-zinc-600 dark:text-zinc-400">
            {failure(session.error)}{" "}
            <Link href="/" className="underline">
              Try another page
            </Link>
          </p>
        )}
      </header>

      <section className="flex flex-col gap-3 rounded-2xl border border-zinc-200 p-6 dark:border-zinc-800">
        <div className="flex flex-wrap items-center gap-3">
          {platform && (
            <a
              href={prompt ? GROK_BOT_APP_URL : undefined}
              onClick={copyPrompt}
              aria-disabled={!prompt}
              className={`${button} ${prompt ? primary : waiting}`}
            >
              Open in Grok Bot
            </a>
          )}
          <a
            href={grokUrl ?? undefined}
            target="_blank"
            rel="noopener"
            aria-disabled={!grokUrl}
            className={`${button} ${!grokUrl ? waiting : platform ? secondary : primary}`}
          >
            Continue in Grok
          </a>
        </div>
        {copied === true && (
          <p className="text-sm">
            Prompt copied. Paste it into a new Grok Bot task ({platform === "mac" ? "⌘V" : "Ctrl+V"}). No Grok Bot yet?{" "}
            <a href={GROK_BOT_DOWNLOAD_URL} target="_blank" rel="noopener" className="underline">
              Download it
            </a>
          </p>
        )}
        {copied === false && prompt && (
          <div className="flex flex-col gap-1 text-sm">
            <p>Your browser wouldn&apos;t let us copy the prompt. Copy it from here and paste it into Grok Bot:</p>
            <textarea readOnly value={prompt} rows={4} className="w-full rounded-lg border border-zinc-300 p-2 font-mono text-xs dark:border-zinc-700" />
          </div>
        )}
        <p className="text-sm text-zinc-500">
          {ready
            ? "Grok opens with this session and reads the shortlist straight from the Eden API."
            : "Available as soon as the page has been read."}{" "}
          <a href={productsUrl(code)} target="_blank" rel="noopener" className="underline">
            See what Grok reads
          </a>
        </p>
      </section>

      {tree.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Categories</h2>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {tree.map((node) => (
              <li key={node.name} className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="font-medium capitalize">
                  {node.name} <span className="text-zinc-500">· {node.count}</span>
                </p>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {node.children.map((child) => `${child.name} (${child.count})`).join(", ")}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {products.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">
            Cheapest per piece <span className="font-normal text-zinc-500">· {total} match</span>
          </h2>
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((p) => (
              <li key={p.id} className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
                {p.image_url && (
                  // Store images come from the store's own CDN; next/image would need every host allowlisted.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.image_url} alt={p.title} className="aspect-square w-full rounded-lg object-cover" loading="lazy" />
                )}
                <a href={p.source_url} target="_blank" rel="noopener" className="font-medium hover:underline">
                  {p.title}
                </a>
                <p className="text-sm">
                  {money(p.price, p.currency)}
                  {p.pieces ? ` · ${p.pieces} pcs` : ""}
                  {p.per_piece !== null ? ` · ${money(p.per_piece, p.currency)}/pc` : ""}
                </p>
                <p className="text-xs text-zinc-500">{p.tree_path.join(" › ")}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
