/**
 * The catch-up view: greets by first name, shows the API's summary and tiles unchanged, says
 * the cards open, opens
 * one tile at a time, closes with Escape, and fetches the dashboard only for a chart tile.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CatchUp } from "@/components/CatchUp";
import type { CatchUpResponse } from "@/lib/types";

const CATCH_UP: CatchUpResponse = {
  as_of: "2026-11-09T17:00:00Z",
  first_name: "Priya",
  role: "hr_manager",
  summary: "On your Engineering and Manufacturing teams (4 jobs): 4 overdue tasks.",
  tiles: [
    { key: "overdue_tasks", label: "Overdue tasks", value: 4, note: "of 4 open tasks" },
    { key: "jobs_past_target", label: "Jobs past target", value: 2, note: "of 2 open jobs" },
    { key: "active_candidates", label: "Active candidates", value: 33, note: "across 4 jobs in your scope" },
  ],
  overdue_tasks: [
    { task_id: "TASK-012", application_id: "APP-060", job_id: "JOB-1", title: "Send the onsite feedback",
      owner_name: "Sam Rivera", days_overdue: 10.4 },
  ],
  overdue_more: 3,
};

/** A fetch that answers /api/catch-up with CATCH_UP and fails /api/dashboard, recording the URLs. */
function stubFetch(): string[] {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      const ok = url.startsWith("/api/catch-up");
      return new Response(JSON.stringify(ok ? CATCH_UP : { error: "Dashboard unavailable." }), {
        status: ok ? 200 : 500,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return urls;
}

describe("CatchUp", () => {
  it("greets by first name and shows the summary and tile values as the API sent them", async () => {
    const urls = stubFetch();
    render(<CatchUp />);
    expect(await screen.findByRole("heading", { level: 1, name: "Hi Priya" })).toBeTruthy();
    expect(screen.getByText(CATCH_UP.summary)).toBeTruthy();
    const tiles = screen.getAllByRole("button", { expanded: false });
    expect(tiles.map((t) => t.textContent)).toEqual([
      "Overdue tasks4of 4 open tasksView",
      "Jobs past target2of 2 open jobsView",
      "Active candidates33across 4 jobs in your scopeView",
    ]);
    // The tile name is the heading of each card, and the "View" cue is not read out as part of its name.
    expect(tiles[0].querySelector(".catchup-tile-label")?.textContent).toBe("Overdue tasks");
    expect(screen.getByRole("button", { name: /^Overdue tasks.*open tasks$/ })).toBeTruthy();
    expect(screen.getByText("Click a card to view charts and analysis.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View full dashboard" }).getAttribute("href")).toBe("/dashboard?view=full");
    expect(urls).toEqual(["/api/catch-up"]);
  });

  it("opens the overdue list without loading the dashboard, and Escape closes it", async () => {
    const urls = stubFetch();
    const user = userEvent.setup();
    render(<CatchUp />);
    const tile = await screen.findByRole("button", { name: /Overdue tasks/ });
    await user.click(tile);
    expect(tile.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Send the onsite feedback")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See all tasks (3 more overdue)" })).toBeTruthy();
    expect(urls).toEqual(["/api/catch-up"]);

    screen.getByRole("link", { name: /See all tasks/ }).focus();
    await user.keyboard("{Escape}");
    expect(tile.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(tile);
  });

  it("loads the dashboard only when a chart tile is opened, and shows its error", async () => {
    const urls = stubFetch();
    const user = userEvent.setup();
    render(<CatchUp />);
    await user.click(await screen.findByRole("button", { name: /Jobs past target/ }));
    expect(await screen.findByText("Dashboard unavailable.")).toBeTruthy();
    expect(urls).toEqual(["/api/catch-up", "/api/dashboard"]);
  });

  it("opens one tile at a time and closes a tile when clicked again", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<CatchUp />);
    const overdue = await screen.findByRole("button", { name: /Overdue tasks/ });
    const past = screen.getByRole("button", { name: /Jobs past target/ });
    await user.click(overdue);
    await user.click(past);
    expect([overdue.getAttribute("aria-expanded"), past.getAttribute("aria-expanded")]).toEqual(["false", "true"]);
    await user.click(past);
    expect(past.getAttribute("aria-expanded")).toBe("false");
  });
});
