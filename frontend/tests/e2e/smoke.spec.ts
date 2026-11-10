/**
 * Smoke tests: every demo user lands on a catch-up view that greets them by first name, can
 * open the pages their role allows, gets the not-found page for the ones it does not, can ask
 * a suggested question (against a stubbed /api/ask) and sees the trace only as admin, can
 * hold a follow-up conversation by keyboard on desktop and phone widths, keeps saved chats per
 * user across reloads and tabs, and an HR Manager can complete one reassignment. It also
 * covers the collapsible navigation, the Ask page's new chat and chat list toggle, and paging.
 */

import { expect, test, type Page } from "@playwright/test";

type Role = "admin" | "hr_manager" | "hr_user";

const USERS: { id: string; label: string; role: Role }[] = [
  { id: "USR-1", label: "Suseel Maddali, Admin", role: "admin" },
  { id: "USR-2", label: "Priya Raman, HR Manager", role: "hr_manager" },
  { id: "USR-3", label: "Daniel Okafor, HR Manager", role: "hr_manager" },
  { id: "USR-4", label: "Sam Rivera, HR User", role: "hr_user" },
  { id: "USR-5", label: "Alex Chen, HR User", role: "hr_user" },
  { id: "USR-6", label: "Jordan Patel, HR User", role: "hr_user" },
];

/** The first name a user is greeted by on the catch-up view. */
function firstName(label: string): string {
  return label.split(" ")[0];
}

const PAGES: { path: string; heading: string | RegExp; nav: string; roles: Role[] }[] = [
  { path: "/dashboard", heading: /^Hi /, nav: "Dashboard", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/ask", heading: "Ask", nav: "Ask", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/jobs", heading: "Jobs", nav: "Jobs", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/tasks", heading: "Tasks", nav: "Tasks", roles: ["admin", "hr_manager", "hr_user"] },
  { path: "/sources", heading: "Sources", nav: "Sources", roles: ["admin", "hr_manager"] },
  { path: "/changes", heading: "Changes", nav: "Changes", roles: ["admin", "hr_manager"] },
  { path: "/quality", heading: "Quality", nav: "Quality", roles: ["admin"] },
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
  await expect(page.getByRole("heading", { level: 1, name: `Hi ${firstName(label)}` })).toBeVisible();
}

const NOT_FOUND = "This page is not available.";

/**
 * A suggested question on an empty Ask chat. Scoped to the suggestions, because a saved chat
 * in the list can carry the same question as its title.
 */
/** Open Ask, which always starts on a new, empty chat even when saved chats exist. */
async function openNewChat(page: Page) {
  await page.goto("/ask");
  await expect(page.getByRole("heading", { name: "What would you like to know?" })).toBeVisible();
  await expect(page.getByLabel("Your question")).toBeVisible();
  await expect(page).not.toHaveURL(/[?&]c=/);
}

function suggestion(page: Page, question: string) {
  return page.getByRole("region", { name: "Try one of these" }).getByRole("button", { name: question });
}

for (const user of USERS) {
  test(`${user.label}: allowed pages open and others show not found`, async ({ page }) => {
    await pickUser(page, user.label);
    const nav = page.getByRole("navigation", { name: "Main" });
    for (const p of PAGES) {
      await expect(nav.getByRole("link", { name: p.nav, exact: true })).toHaveCount(p.roles.includes(user.role) ? 1 : 0);
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
    await openNewChat(page);
    await suggestion(page, CHIP[role]).click();
    await expect(page.getByText("Verified", { exact: true })).toBeVisible();
    expect(asked).toEqual([CHIP[role]]);
    await expect(page.getByRole("button", { name: "Open evidence for APP-062" }).first()).toBeVisible();
    // The stub sends the admin fields to every role, so this checks the page hides the trace.
    if (role === "admin") {
      await page.getByRole("button", { name: "Show trace" }).click();
      await expect(page.getByText("pending_tasks")).toBeVisible();
    } else {
      await expect(page.getByRole("button", { name: "Show trace" })).toHaveCount(0);
    }
  });
}

/** Stub /api/ask with a numbered answer citing APP-062 and keep each request body. */
async function stubAsk(page: Page): Promise<Record<string, unknown>[]> {
  const bodies: Record<string, unknown>[] = [];
  await page.route("**/api/ask", async (route) => {
    bodies.push(JSON.parse(route.request().postData() ?? "{}"));
    await route.fulfill({
      json: {
        answer: `Answer ${bodies.length}: start with the offer follow-up [APP-062].\n\n| Candidate | Stage | Days waiting |\n|---|---|---|\n| APP-062 | Offer | 6 |\n| APP-071 | Onsite | 3 |`,
        status: "answered",
        verified: true,
        label: "verified",
        citations: ["APP-062", "APP-071"],
        model: "claude-haiku-5-5",
        as_of: "2026-11-09T17:00:00Z",
        job_id: null,
        source: "live",
      },
    });
  });
  return bodies;
}

test("a follow-up question sends the earlier turn as history", async ({ page }) => {
  const bodies = await stubAsk(page);
  await pickUser(page, "Sam Rivera, HR User");
  await openNewChat(page);
  const box = page.getByLabel("Your question");
  await box.fill("Who is waiting on me?");
  await box.press("Enter");
  await expect(page.getByText(/^Answer 1:/)).toBeVisible();
  await box.fill("And which one is oldest?");
  await box.press("Enter");
  await expect(page.getByText(/^Answer 2:/)).toBeVisible();
  expect(bodies[0].history).toBeUndefined();
  expect(bodies[1].history).toEqual([
    { question: "Who is waiting on me?", answer: expect.stringContaining("Answer 1:"), citations: ["APP-062", "APP-071"] },
  ]);
});

test("the conversation works by keyboard alone", async ({ page }) => {
  await stubAsk(page);
  await pickUser(page, "Sam Rivera, HR User");
  await openNewChat(page);
  await expect(page.getByLabel("Your question")).toBeVisible();
  for (let i = 0; i < 200 && !(await page.getByLabel("Your question").evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(page.getByLabel("Your question")).toBeFocused();
  await page.keyboard.type("What should I do today?");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/^Answer 1:/)).toBeVisible();
  const toggle = page.getByRole("button", { name: "Show evidence" });
  for (let i = 0; i < 200 && !(await toggle.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Shift+Tab");
  }
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Hide evidence" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Records cited")).toBeVisible();
});

test("at phone width the Ask page never scrolls sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await stubAsk(page);
  await pickUser(page, "Sam Rivera, HR User");
  await openNewChat(page);
  const box = page.getByLabel("Your question");
  await box.fill("Who is waiting on me?");
  await box.press("Enter");
  await expect(page.getByText(/^Answer 1:/)).toBeVisible();
  await page.getByRole("button", { name: "Show evidence" }).click();
  const [scroll, inner] = await page.evaluate(() => [document.scrollingElement!.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
  // Send stays on the same row as the question box.
  const boxArea = (await box.boundingBox())!;
  const send = (await page.getByRole("button", { name: "Send" }).boundingBox())!;
  expect(send.y).toBeLessThan(boxArea.y + boxArea.height);
  // New chat in the header goes back to the centered welcome, and picking a chat in the Chats
  // drawer opens it and closes the drawer. The stubbed answer is not saved, so the newest chat
  // keeps its default title.
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page.getByRole("heading", { name: "What would you like to know?" })).toBeVisible();
  await page.getByRole("button", { name: "Chats", exact: true }).click();
  await page.getByRole("dialog").locator(".session-open").first().click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/[?&]c=CONV-/);
});

test("the chat list can be hidden and shown, and the choice is remembered", async ({ page }) => {
  await pickUser(page, "Sam Rivera, HR User");
  await openNewChat(page);
  const panel = page.getByRole("navigation", { name: "Saved chats" });
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "Hide chats" }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Show chats" })).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(page.getByRole("button", { name: "Show chats" })).toBeVisible();
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "Show chats" }).click();
  await expect(panel).toBeVisible();
});

test("the main menu collapses to icons, keeps its link names, and remembers the choice", async ({ page }) => {
  await pickUser(page, "Suseel Maddali, Admin");
  const nav = page.getByRole("navigation", { name: "Main" });
  await nav.getByRole("button", { name: "Collapse menu" }).click();
  const quality = nav.getByRole("link", { name: "Quality", exact: true });
  await expect(quality).toBeVisible();
  // The rail is narrow: the link is little more than its icon. The rail animates, so wait for it.
  await expect.poll(async () => (await quality.boundingBox())!.width).toBeLessThan(60);
  await page.reload();
  await expect(nav.getByRole("button", { name: "Expand menu" })).toHaveAttribute("aria-expanded", "false");
  await quality.click();
  await expect(page.getByRole("heading", { level: 1, name: "Quality" })).toBeVisible();
  await nav.getByRole("button", { name: "Expand menu" }).click();
  await expect(nav.getByRole("button", { name: "Collapse menu" })).toHaveAttribute("aria-expanded", "true");
});

test("long task groups show five at a time with page buttons", async ({ page }) => {
  await pickUser(page, "Suseel Maddali, Admin");
  await page.goto("/tasks");
  const pager = page.getByRole("group", { name: "Tasks: People, pages" });
  await expect(pager).toContainText("Showing 1 to 5 of");
  await pager.getByRole("button", { name: "Next page" }).click();
  await expect(pager).toContainText("Showing 6 to");
  await expect(pager.getByRole("button", { name: "Next page" })).toBeDisabled();
});

// Runs before the reassignment test, which can change Sam Rivera's scope and so the recordings that match.
test("a saved chat survives reloads and new tabs, stays with its user, and can be renamed and deleted", async ({ page, context }) => {
  const name = `Saved chat ${Date.now()}`;
  const panel = () => page.getByRole("navigation", { name: "Saved chats" });
  await pickUser(page, "Sam Rivera, HR User");
  await openNewChat(page);
  await suggestion(page, CHIP.hr_user).click();
  await expect(page.getByText("Recorded answer", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/[?&]c=CONV-[a-z0-9]{12}/);
  const answer = (await page.locator(".bubble-assistant .answer").first().innerText()).slice(0, 40);

  await panel().getByRole("button", { name: `More actions for ${CHIP.hr_user}` }).first().click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  await page.getByLabel(`New name for ${CHIP.hr_user}`).fill(name);
  await page.getByLabel(`New name for ${CHIP.hr_user}`).press("Enter");
  await expect(panel().getByRole("button", { name: new RegExp(`^${name}`) })).toHaveAttribute("aria-current", "true");

  await page.reload();
  await expect(page.getByText(answer, { exact: false })).toBeVisible();

  // A new tab with the chat's address reopens it; a plain /ask starts a new chat instead.
  const second = await context.newPage();
  await second.goto(page.url());
  await expect(second.getByText(answer, { exact: false })).toBeVisible();
  await expect(second.getByRole("navigation", { name: "Saved chats" }).getByRole("button", { name: new RegExp(`^${name}`) })).toBeVisible();
  await second.close();

  await pickUser(page, "Alex Chen, HR User");
  await page.goto("/ask");
  await expect(panel()).toBeVisible();
  await expect(panel().getByText(name)).toHaveCount(0);

  await pickUser(page, "Sam Rivera, HR User");
  await page.goto("/ask");
  await expect(panel().getByRole("button", { name: new RegExp(`^${name}`) })).toBeVisible();

  await panel().getByRole("button", { name: `More actions for ${name}` }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await panel().getByRole("group", { name: `Delete ${name}?` }).getByRole("button", { name: "Delete" }).click();
  await expect(panel().getByText(name)).toHaveCount(0);
  await page.reload();
  await expect(panel()).toBeVisible();
  await expect(panel().getByText(name)).toHaveCount(0);
});

test("an InfoTip opens on a tap and closes on a tap outside", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 740 }, hasTouch: true, isMobile: true, baseURL: "http://localhost:3000" });
  const page = await context.newPage();
  await pickUser(page, "Sam Rivera, HR User");
  await page.goto("/tasks");
  // Wait for the tasks to load, so the page is interactive before the tap.
  await expect(page.getByRole("heading", { name: "Rules for derived tasks" })).toBeVisible();
  await page.getByRole("button", { name: "About Tasks" }).tap();
  const tip = page.getByText("Overdue and pending work, most overdue first.");
  await expect(tip).toBeVisible();
  await page.getByRole("heading", { level: 1, name: "Tasks" }).tap();
  await expect(tip).toBeHidden();
  await context.close();
});

test("an InfoTip card opens next to its icon and stays inside the window", async ({ page }) => {
  await pickUser(page, "Alex Chen, HR User");
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Rules for derived tasks" })).toBeVisible();
  const icon = page.getByRole("button", { name: "About Tasks" });
  await icon.click();
  const card = page.getByRole("dialog", { name: "Tasks" });
  await expect(card).toContainText("Overdue and pending work, most overdue first.");
  const i = (await icon.boundingBox())!;
  // The kit animates the card in, so wait for it to settle beside the icon.
  await expect.poll(async () => Math.abs((await card.boundingBox())!.x - i.x)).toBeLessThanOrEqual(24);
  const c = (await card.boundingBox())!;
  expect(c.x).toBeGreaterThanOrEqual(0);
  expect(c.x + c.width).toBeLessThanOrEqual(page.viewportSize()!.width);
});

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

for (const user of [USERS[0], USERS[1], USERS[3]]) {
  for (const width of [1280, 390]) {
    test(`${user.label} at ${width}px: catch-up tiles open their detail on demand`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await pickUser(page, user.label);
      await expect(page.getByText(/: .*\.$/).first()).toBeVisible();
      const tiles = page.getByRole("region", { name: "What needs attention" }).getByRole("button");
      await expect(tiles).toHaveCount(5);
      await expect(page.getByText("Click a card to view charts and analysis.")).toBeVisible();
      // Nothing heavy until a tile is opened: no chart and no dashboard request yet.
      await expect(page.getByRole("heading", { name: "Pipeline funnel" })).toHaveCount(0);
      const tile = page.getByRole("button", { name: /Active candidates/ });
      await tile.focus();
      await page.keyboard.press("Enter");
      await expect(tile).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByRole("heading", { name: "Pipeline funnel" })).toBeVisible();
      await page.getByRole("button", { name: /Overdue tasks/ }).click();
      await expect(page.getByRole("heading", { name: "Pipeline funnel" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: /See all tasks/ })).toBeVisible();
      await page.getByRole("link", { name: /See all tasks/ }).focus();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button", { name: /Overdue tasks/ })).toBeFocused();
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scroll).toBeLessThanOrEqual(width);
    });
  }
}

test("View full dashboard shows every chart and leads back to catch-up", async ({ page }) => {
  await pickUser(page, "Suseel Maddali, Admin");
  await page.getByRole("link", { name: "View full dashboard" }).click();
  await expect(page).toHaveURL(/\/dashboard\?view=full$/);
  await expect(page.getByRole("heading", { level: 1, name: "Full dashboard" })).toBeVisible();
  for (const title of ["Pipeline funnel", "Days open vs target", "Applicants per week", "Source quality",
    "Median time in each stage", "Withdrawals by reason", "Recruiter load", "Offer acceptance"]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
  await page.getByRole("link", { name: "Back to catch-up" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Hi Suseel" })).toBeVisible();
});

test("an HR User's full dashboard has no recruiter load chart", async ({ page }) => {
  await pickUser(page, "Sam Rivera, HR User");
  await page.goto("/dashboard?view=full");
  await expect(page.getByRole("heading", { name: "Pipeline funnel" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recruiter load" })).toHaveCount(0);
});

test("dashboard filters live in the URL and Clear filters removes them", async ({ page }) => {
  await pickUser(page, "Suseel Maddali, Admin");
  await page.goto("/dashboard?view=full");
  await page.getByLabel("Team").selectOption({ label: "Engineering" });
  await expect(page).toHaveURL(/team=TEAM-1/);
  await page.getByLabel("Applied in").selectOption("90");
  await expect(page).toHaveURL(/days=90/);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/dashboard\?view=full$/);
  await expect(page.getByRole("button", { name: "Clear filters" })).toHaveCount(0);
});

test("How it works opens from the landing page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "How it works" }).click();
  await expect(page.getByRole("dialog", { name: "How RecruitAssist works" })).toContainText("Read-only assistant");
});
