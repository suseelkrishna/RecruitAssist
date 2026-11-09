"use client";

/**
 * Load data for a page with one api.ts function and track its state: loading, ready, error,
 * or not found. A plain useEffect, so there is no data-fetching library.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError, isNotFound } from "@/lib/api";

export type Load<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; message: string }
  | { state: "not_found" };

/** Run `load` when `key` changes, and again when reload() is called. */
export function useLoad<T>(load: () => Promise<T>, key: string): Load<T> & { reload: () => void } {
  const [round, setRound] = useState(0);
  const [stored, setStored] = useState<{ for: string; result: Load<T> } | null>(null);
  const reload = useCallback(() => setRound((n) => n + 1), []);
  const requestKey = `${key}#${round}`;

  useEffect(() => {
    let current = true;
    load()
      .then((data) => current && setStored({ for: requestKey, result: { state: "ready", data } }))
      .catch((error: unknown) => {
        if (!current) return;
        const result: Load<T> = isNotFound(error)
          ? { state: "not_found" }
          : { state: "error", message: error instanceof ApiError ? error.message : "The data could not be loaded." };
        setStored({ for: requestKey, result });
      });
    return () => {
      current = false;
    };
    // `load` is recreated on each render; requestKey names what it loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  // Until the answer for the current key arrives, the page is loading.
  const result: Load<T> = stored && stored.for === requestKey ? stored.result : { state: "loading" };
  return { ...result, reload };
}
