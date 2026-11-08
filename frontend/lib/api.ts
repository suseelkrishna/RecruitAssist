/**
 * The only file that calls the backend. Each route has one small typed function, and all of
 * them go through request(), which adds the X-Demo-User header and turns error statuses into
 * errors the pages can show. Pages render what these functions return and compute nothing.
 */

import { clearDemoUser, getDemoUser } from "@/lib/user";
import type {
  AskBody,
  AskResult,
  DashboardFilters,
  DashboardResponse,
  Evidence,
  JobDetail,
  JobsResponse,
  MeResponse,
  UsersResponse,
} from "@/lib/types";

/** An error response from the API, with its status and the backend's friendly message. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** True when the error means the record does not exist or is outside the user's scope. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/**
 * Call one backend route with plain fetch. 401 means no demo user is picked, so the person is
 * sent to the landing page to pick one. Any other error status throws an ApiError.
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const user = getDemoUser();
  if (user) headers.set("X-Demo-User", user);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    clearDemoUser();
    // A full page load, not a client-side push: this module has no router, and a fresh load
    // drops any data fetched for the previous user.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (typeof window !== "undefined" && window.location.pathname !== "/") window.location.href = "/";
    throw new ApiError(401, "Choose a demo user first.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.error ?? "Something went wrong. Try again in a moment.");
  }
  return (await response.json()) as T;
}

/** A query string from the given values, leaving out empty ones. */
function query(values: Record<string, string | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** GET /api/users: the demo users to pick from on the landing page. */
export function getUsers(): Promise<UsersResponse> {
  return request("/api/users");
}

/** GET /api/me: who the current demo user is, their role, and their scope. */
export function getMe(): Promise<MeResponse> {
  return request("/api/me");
}

/** GET /api/dashboard: every dashboard metric for the filters, in one call. */
export function getDashboard(filters: DashboardFilters): Promise<DashboardResponse> {
  return request(`/api/dashboard${query(filters)}`);
}

/** GET /api/jobs: the jobs in scope, with the columns and filter choices of the jobs page. */
export function getJobs(): Promise<JobsResponse> {
  return request("/api/jobs");
}

/** GET /api/jobs/{id}: one job with its funnel, candidates, top 3, tasks, and reassign options. */
export function getJob(jobId: string): Promise<JobDetail> {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`);
}

/** POST /api/jobs/{id}/assignment: give the job to another recruiter. The only write in the app. */
export function reassignJob(jobId: string, recruiterUserId: string, reason?: string): Promise<JobDetail> {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/assignment`, {
    method: "POST",
    body: JSON.stringify({ recruiter_user_id: recruiterUserId, ...(reason ? { reason } : {}) }),
  });
}

/** GET /api/candidates/{id}: the evidence for one application, with contact details masked. */
export function getCandidate(applicationId: string): Promise<Evidence> {
  return request(`/api/candidates/${encodeURIComponent(applicationId)}`);
}

/** POST /api/ask: ask the assistant one question and wait for the full, checked answer. */
export function ask(body: AskBody): Promise<AskResult> {
  return request("/api/ask", { method: "POST", body: JSON.stringify(body) });
}
