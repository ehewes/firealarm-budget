"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { account, EdenApiError, money, type Purchase } from "@/lib/api";
import { currentUser, existingToken } from "@/lib/supabase";

const OUTCOME: Partial<Record<Purchase["status"], string>> = {
  executing: "Card ready. Checking out…",
  completed: "Order placed",
  failed: "This purchase didn't go through",
  cancelled: "Cancelled. Nothing was bought.",
};

/**
 * The only place a purchase is approved (CLAUDE.md rule 2): the signed-in owner, on Eden.
 * Everything shown comes from the API; prices are re-checked on the store when they confirm.
 */
export function ConfirmView({ id }: { id: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [needsAccount, setNeedsAccount] = useState(false);
  const [purchase, setPurchase] = useState<Purchase | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** The purchase, if the visitor is signed in to a real account (else null: they must sign in). */
  const fetchPurchase = useCallback(async () => {
    const [t, user] = await Promise.all([existingToken(), currentUser()]);
    if (!t || !user || user.is_anonymous) return null;
    return { token: t, purchase: await account.purchase(t, id) };
  }, [id]);

  const show = useCallback((found: { token: string; purchase: Purchase } | null) => {
    if (!found) {
      setNeedsAccount(true);
      return;
    }
    setToken(found.token);
    setPurchase(found.purchase);
  }, []);

  useEffect(() => {
    let stopped = false;
    fetchPurchase().then(
      (found) => !stopped && show(found),
      (e) => !stopped && setError(e instanceof Error ? e.message : "Couldn't load this purchase."),
    );
    return () => {
      stopped = true;
    };
  }, [fetchPurchase, show]);

  // While the demo checkout runs, follow it to the end.
  useEffect(() => {
    if (purchase?.status !== "executing") return;
    const timer = setTimeout(() => fetchPurchase().then(show, () => undefined), 1500);
    return () => clearTimeout(timer);
  }, [purchase, fetchPurchase, show]);

  const act = async (fn: () => Promise<Purchase>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setPurchase(await fn());
    } catch (e) {
      if (e instanceof EdenApiError && e.code === "price_changed") {
        setNotice(e.message);
        show(await fetchPurchase());
      } else {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  };

  if (needsAccount) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-2xl font-semibold">Sign in to confirm this purchase</h1>
        <p className="text-zinc-600 dark:text-zinc-400">Only the account your agent is buying for can approve it.</p>
        <Link
          href={`/dashboard?next=${encodeURIComponent(`/confirm/${id}`)}`}
          className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white dark:bg-white dark:text-black"
        >
          Sign in
        </Link>
      </main>
    );
  }

  if (!purchase) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        {error ? (
          <h1 className="text-2xl font-semibold">{error}</h1>
        ) : (
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-black dark:border-zinc-700 dark:border-t-white" />
        )}
      </main>
    );
  }

  const open = purchase.status === "pending" || purchase.status === "price_changed";
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <Link href="/dashboard" className="text-sm uppercase tracking-widest text-zinc-500">
          Eden Matrix · your account
        </Link>
        <h1 className="text-3xl font-semibold">
          {open ? "Your agent wants to buy this" : OUTCOME[purchase.status] ?? purchase.status}
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          From {purchase.store}
          {purchase.session_code && (
            <>
              {" "}
              · session{" "}
              <Link href={`/s/${purchase.session_code}`} className="underline">
                {purchase.session_code}
              </Link>
            </>
          )}
        </p>
      </header>

      {notice && <p className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">{notice}</p>}
      {error && <p className="rounded-xl bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-100">{error}</p>}

      <ul className="flex flex-col gap-3">
        {purchase.items.map((item) => (
          <li key={item.id} className="flex items-center gap-4 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
            {item.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.image_url} alt={item.title} className="h-16 w-16 rounded-lg object-cover" />
            )}
            <a href={item.source_url} target="_blank" rel="noopener" className="flex-1 font-medium hover:underline">
              {item.title}
            </a>
            <span>{money(item.price, item.currency)}</span>
          </li>
        ))}
      </ul>

      <section className="flex flex-col gap-3 rounded-2xl border border-zinc-200 p-6 dark:border-zinc-800">
        <p className="text-lg">
          Total <span className="font-semibold">{money(purchase.total, purchase.currency)}</span>
        </p>
        {purchase.card && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Eden demo card •••• {purchase.card.last4} · limit {money(purchase.card.limit, purchase.currency)}
          </p>
        )}
        {purchase.status === "completed" && <p className="text-sm">Order {purchase.order_ref}</p>}
        {purchase.error && <p className="text-sm text-zinc-500">{purchase.error}</p>}
        {open && (
          <>
            <p className="text-sm text-zinc-500">
              We re-check each price and stock on {purchase.store} before issuing the card. If anything changed, you
              see the new total first.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => account.confirm(token!, id))}
                className="rounded-full bg-black px-6 py-3 text-base font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {busy ? "Checking prices…" : `Confirm and pay ${money(purchase.total, purchase.currency)}`}
              </button>
              <button type="button" disabled={busy} onClick={() => act(() => account.cancel(token!, id))} className="text-sm text-zinc-500 underline">
                Cancel
              </button>
            </div>
            <p className="text-xs text-zinc-500">Expires {new Date(purchase.expires_at).toLocaleTimeString()}.</p>
          </>
        )}
      </section>
    </main>
  );
}
