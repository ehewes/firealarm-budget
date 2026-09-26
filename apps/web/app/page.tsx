import Link from "next/link";

import { PrefixForm } from "@/components/prefix-form";

const EXAMPLE = "https://www.joinfleek.com/collections/april-eom-rl-drop";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-3">
        <p className="text-sm uppercase tracking-widest text-zinc-500">Eden Matrix</p>
        <h1 className="text-4xl font-semibold leading-tight">Put our domain in front of any store page.</h1>
        <p className="text-lg text-zinc-600 dark:text-zinc-400">
          We read the page, sort every product into categories, and hand it to Grok to recommend what fits your
          rules.
        </p>
      </div>
      <code className="rounded-xl bg-zinc-100 p-4 text-sm leading-6 break-all dark:bg-zinc-900">
        {EXAMPLE}
        <br />↓<br />
        go.edenmatrix.xyz/{EXAMPLE}
      </code>
      <PrefixForm />
      <p className="text-sm text-zinc-500">
        Try it:{" "}
        <Link href={`/${EXAMPLE}`} className="underline">
          the April EOM Ralph Lauren drop
        </Link>
        {" · "}
        <Link href="/dashboard" className="underline">
          Your account, agent card and Grok Bot
        </Link>
      </p>
    </main>
  );
}
