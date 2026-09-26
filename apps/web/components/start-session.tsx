"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { accessToken } from "@/lib/supabase";
import { hostOf } from "@/lib/target";

/** The prefix route's only job: sign the visitor in (anonymously if new), start a session, move on. */
export function StartSession({ target }: { target: string }) {
  const router = useRouter();
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Strict Mode runs effects twice in development; a double POST would mint two sessions.
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const created = await api.createSession(target, await accessToken());
        // Replace, not push: refreshing the session page must not start another session.
        router.replace(`/s/${created.code}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
      }
    })();
  }, [target, router]);

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-sm uppercase tracking-widest text-zinc-500">Eden Matrix</p>
      {error ? (
        <>
          <h1 className="text-2xl font-semibold">We couldn&apos;t open {hostOf(target)}</h1>
          <p className="text-zinc-600 dark:text-zinc-400">{error}</p>
          <Link href="/" className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white dark:bg-white dark:text-black">
            Try another page
          </Link>
        </>
      ) : (
        <>
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-black dark:border-zinc-700 dark:border-t-white" />
          <h1 className="text-2xl font-semibold">Reading {hostOf(target)}…</h1>
          <p className="max-w-full truncate text-sm text-zinc-500">{target}</p>
        </>
      )}
    </main>
  );
}
