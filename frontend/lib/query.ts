"use client";

/**
 * Filters kept in the URL query, so a copied link reproduces the same view. Reading and
 * writing go through Next.js navigation, which keeps the browser history tidy.
 */

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** The current filter values by name, a function that sets one, and one that clears them all. */
export function useQueryFilters<K extends string>(
  names: readonly K[],
): [Record<K, string>, (name: K, value: string) => void, () => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const values = Object.fromEntries(names.map((n) => [n, params.get(n) ?? ""])) as Record<K, string>;

  function set(name: K, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(name, value);
    else next.delete(name);
    const text = next.toString();
    router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }

  /** Remove every filter this page owns from the URL, keeping any other query values. */
  function clear() {
    const next = new URLSearchParams(params.toString());
    for (const name of names) next.delete(name);
    const text = next.toString();
    router.replace(text ? `${pathname}?${text}` : pathname, { scroll: false });
  }

  return [values, set, clear];
}
