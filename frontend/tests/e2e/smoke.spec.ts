/**
 * Smoke tests: every demo user can open the pages their role allows, gets the not-found page
 * for the ones it does not, can ask a suggested question (against a stubbed /api/ask), and an
 * HR Manager can complete one reassignment.
 */

import { expect, test, type Page } from "@playwright/test";

type Role = "admin" | "hr_manager" | "hr_user";

const USERS: { id: string; label: string; role: Role }[] = [
  { id: "USR-1", label: "Morgan Lee, Admin", role: "admin" },
  { id: "USR-2", label: "Priya Raman, HR Manager", role: "hr_manager" },
  { id: "USR-3", label: "Daniel Okafor, HR Manager", role: "hr_manager" },
  { id: "USR-4", label: "Sam Rivera, HR User", role: "hr_user" },
  { id: "USR-5", label: "Alex Chen, HR User", role: "hr_user" },
  { id: "USR-6", label: "Jordan Patel, HR User", role: "hr_user" },
];

const PAGES: { path: string; heading: string; roles: Role[] }[] = [
  { path: "/dashboard", heading: "Dashboard", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/ask", heading: "Ask", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/jobs", heading: "Jobs", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/tasks", heading: "Tasks", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/sources", heading: "Sources", roles: ["admin", "hr_manager"] },
  { path: "/changes", heading: "Changes", roles: ["admin", "hr_manager"] },
  { path: "/quality", heading: "Quality", roles: ["admin", "hr_manager", "hr_user"] },
];

const CHIP: Record<Role, string> = {
  admin: "Company-wide pipeline health",
  hr_manager: "Where is my team losing candidates?",
  hr_user: "What should I do today?",
};

/** Pick a demo user on the landing page, as a person would. */
async function pickUser(page: Page, label: string) {
  await page.goto("/");
  await page.getByRole("button", { name: label }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
}

const NOT_FOUND = "This page is not available.";

for (const user of USERS) {
  test(`${user.label}: allowed pages open and others show not found`, async ({ page }) => {
    await pickUser(page, user.label);
    const nav = page.getByRole("navigation", { name: "Main" });
    for (const p of PAGES) {
      await expect(nav.getByRole("link", { name: p.heading, exact: true })).toHaveCount(p.roles.includes(user.role) ? 1 : 0);
    }
    for (const p of PAGES) {
      const allowed = p.roles.includes(user.role);
      await page.goto(p.path);
      if (allowed) {
        await expect(page.getByRole("heading", { level: 1, name: p.heading })).toBeVisible();
        await expect(page.getByText(NOT_FOUND)).toHaveCount(0);
      } else {
        await expect(page.getByText(NOT_FOUND)).toBeVisible();
      }
    }
  });
}

test("an HR User gets not found for a job and a candidate outside their scope", async ({ page }) => {
  await pickUser(page, "Sam Rivera, HR User");
  // JOB-3 is on a team Sam Rivera does not recruit for, and no test reassigns it.
  await page.goto("/jobs/JOB-3");
  await expect(page.getByText(NOT_FOUND)).toBeVisible();
  await page.goto("/candidates/APP-062");
  await expect(page.getByText(NOT_FOUND)).toBeVisible();
  await page.goto("/jobs/JOB-1");
  await expect(page.getByRole("heading", { level: 1, name: "Senior Controls Engineer" })).toBeVisible();
});

test("no demo user sends the person to the landing page", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Choose a demo user" })).toBeVisible();
});

for (const role of ["admin", "hr_manager", "hr_user"] as Role[]) {
  test(`${role}: a suggested question gets a verified, cited answer from a stubbed backend`, async ({ page }) => {
    const user = USERS.find((u) => u.role === role)!;
    const asked: string[] = [];
    await page.route("**/api/ask", async (route) => {
      asked.push(JSON.parse(route.request().postData() ?? "{}").question);
      await route.fulfill({
        json: {
          answer: "Start with the overdue offer follow-up [APP-062], then the onsite reply [APP-071].",
          status: "answered",
          verified: true,
          label: "verified",
          citations: ["APP-062", "APP-071", "TASK-011"],
          steps: [{ tool: "pending_tasks", input: {}, rows: 6, is_error: false, ms: 20 }],
          usage: { api_calls: 2, input_tokens: 10, output_tokens: 200, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, cache_hits: 1 },
          latency_ms: 1200,
          estimated_cost_usd: 0.01,
          model: "claude-opus-5-5",
          served_by: "claude-opus-5-5",
          verifier: { passed: true, failures: [], checks: {} },
          as_of: "2026-11-09T17:00:00Z",
          job_id: null,
          source: "live",
        },
      });
    });
    await pickUser(page, user.label);
    await page.goto("/ask");
    await page.getByRole("button", { name: CHIP[role] }).click();
    await expect(page.getByText("Verified", { exact: true })).toBeVisible();
    expect(asked).toEqual([CHIP[role]]);
    await expect(page.getByRole("button", { name: "Open evidence for APP-062" }).first()).toBeVisible();
    await page.getByText("Behind the scenes").click();
    await expect(page.getByText("pending_tasks")).toBeVisible();
  });
}

test("an HR Manager reassigns a job and the change log records it", async ({ page }) => {
  await pickUser(page, "Priya Raman, HR Manager");
  await page.goto("/jobs/JOB-2");
  const recruiterCard = page.locator("section", { has: page.getByRole("heading", { name: "Recruiter" }) });
  const before = (await recruiterCard.locator("p").first().textContent())?.trim() ?? "";
  const select = page.getByLabel("Reassign to");
  const target = (await select.locator("option").first().textContent())?.trim() ?? "";
  await page.getByLabel("Reason (optional)").fill("Smoke test reassignment");
  await page.getByRole("button", { name: "Reassign" }).click();
  await expect(page.getByRole("alertdialog")).toContainText(`Reassign JOB-2 from ${before} to ${target}?`);
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(`JOB-2 is now assigned to ${target}.`, { exact: false })).toBeVisible();
  await expect(recruiterCard.locator("p").first()).toHaveText(target);
  await page.goto("/changes?kind=reassignment");
  // The log is newest first; earlier runs against the same server may have added older rows.
  const newest = page.getByRole("table").getByRole("row").nth(1);
  await expect(newest).toContainText(`JOB-2 recruiter: ${before} to ${target}`);
  await expect(newest).toContainText("Reason: Smoke test reassignment");
  await expect(newest).toContainText("Priya Raman");
});

test("dashboard filters live in the URL and Clear filters removes them", async ({ page }) => {
  await pickUser(page, "Morgan Lee, Admin");
  await page.getByLabel("Team").selectOption({ label: "Engineering" });
  await expect(page).toHaveURL(/team=TEAM-1/);
  await page.getByLabel("Applied in").selectOption("90");
  await expect(page).toHaveURL(/days=90/);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("button", { name: "Clear filters" })).toHaveCount(0);
});

test("How it works opens from the landing page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "How it works" }).click();
  await expect(page.getByRole("dialog", { name: "How RecruitAssist works" })).toContainText("Read-only assistant");
});
