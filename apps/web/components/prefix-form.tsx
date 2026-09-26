"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Paste a store URL instead of editing the address bar; lands on the same prefix route. */
export function PrefixForm() {
  const router = useRouter();
  const [value, setValue] = useState("");
  return (
    <form
      className="flex w-full flex-col gap-3 sm:flex-row"
      onSubmit={(e) => {
        e.preventDefault();
        const url = value.trim();
        if (url) router.push(`/${url}`);
      }}
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="https://www.joinfleek.com/collections/nike"
        aria-label="Store page URL"
        className="flex-1 rounded-full border border-zinc-300 px-5 py-3 text-base dark:border-zinc-700 dark:bg-zinc-900"
      />
      <button type="submit" className="rounded-full bg-black px-6 py-3 font-medium text-white dark:bg-white dark:text-black">
        Open in Eden
      </button>
    </form>
  );
}
