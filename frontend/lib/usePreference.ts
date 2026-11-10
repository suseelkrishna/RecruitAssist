"use client";

/**
 * A remembered on or off choice for this browser, such as a collapsed menu or a hidden chat
 * list. It is a convenience only: the value lives in localStorage and falls back to the
 * default when there is none or storage is blocked. The server render always uses the
 * default, and the saved choice takes over once the page is running in the browser.
 */

import { useCallback, useSyncExternalStore } from "react";

const PREFIX = "recruitassist:pref:";
const EVENT = "recruitassist:pref";

/** Read a saved choice, or null when there is none or storage is blocked. */
function read(name: string): boolean | null {
  try {
    const value = window.localStorage.getItem(PREFIX + name);
    return value === null ? null : value === "1";
  } catch {
    return null;
  }
}

/** Save a choice and tell every hook in this tab, ignoring blocked storage. */
function write(name: string, value: boolean): void {
  try {
    window.localStorage.setItem(PREFIX + name, value ? "1" : "0");
  } catch {
    // Blocked storage only means the choice is not remembered.
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { name, value } }));
}

/** Call back when a choice changes in this tab or another one. */
function subscribe(callback: () => void): () => void {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

// The value set in this tab, kept for when storage is blocked and read() cannot see it.
const local = new Map<string, boolean>();

/** The current value and a setter that also saves it. */
export function usePreference(name: string, fallback: boolean): [boolean, (value: boolean) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => read(name) ?? local.get(name) ?? fallback,
    () => fallback,
  );
  const set = useCallback(
    (next: boolean) => {
      local.set(name, next);
      write(name, next);
    },
    [name],
  );
  return [value, set];
}
