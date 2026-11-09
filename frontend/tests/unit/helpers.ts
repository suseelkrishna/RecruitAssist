/** Test helpers: a fake fetch that records calls and answers with a fixed status and body. */

import { vi } from "vitest";

export type Call = { url: string; init: RequestInit };

/** Replace fetch with one that returns `body` with `status`, and return the list of calls made. */
export function fakeFetch(status: number, body: unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}
