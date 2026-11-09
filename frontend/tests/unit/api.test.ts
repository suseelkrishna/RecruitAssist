/** The request() helper: it adds the demo user header, sends 401 to the landing page, and marks 404. */

import { describe, expect, it } from "vitest";
import { ApiError, getJob, isNotFound, request } from "@/lib/api";
import { getDemoUser, setDemoUser } from "@/lib/user";
import { fakeFetch } from "./helpers";

describe("request", () => {
  it("adds the X-Demo-User header from the cookie", async () => {
    setDemoUser("USR-4");
    const calls = fakeFetch(200, { ok: true });
    await request("/api/me");
    expect(calls).toHaveLength(1);
    expect(new Headers(calls[0].init.headers).get("X-Demo-User")).toBe("USR-4");
  });

  it("sends no header when no demo user is picked", async () => {
    const calls = fakeFetch(200, {});
    await request("/api/users");
    expect(new Headers(calls[0].init.headers).has("X-Demo-User")).toBe(false);
  });

  it("on 401 forgets the demo user and throws a 401 error", async () => {
    setDemoUser("USR-9");
    fakeFetch(401, { error: "Unknown user" });
    const error = await request("/api/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(getDemoUser()).toBeNull();
  });

  it("on 404 throws an error the pages treat as not found", async () => {
    setDemoUser("USR-4");
    fakeFetch(404, { error: "JOB-2 is not in your scope" });
    const error = await getJob("JOB-2").catch((e: unknown) => e);
    expect(isNotFound(error)).toBe(true);
    expect((error as ApiError).message).toBe("JOB-2 is not in your scope");
  });

  it("passes the backend's message through for other errors", async () => {
    fakeFetch(400, { error: "days must be one of 30, 90, 180, got 45." });
    const error = (await request("/api/dashboard?days=45").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(400);
    expect(error.message).toContain("30, 90, 180");
    expect(isNotFound(error)).toBe(false);
  });
});
