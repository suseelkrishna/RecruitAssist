/** Chart cards: "View as table" swaps the chart for a table of the same values, as the API gave them. */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DaysOpenChart } from "@/components/charts/DaysOpenChart";
import { TimeInStageChart } from "@/components/charts/TimeInStageChart";
import type { DashboardResponse } from "@/lib/types";

const DATA = {
  time_in_stage: {
    metric: "time_in_stage",
    as_of: "2026-11-09T17:00:00Z",
    takeaway: "Candidates spend longest in Onsite, a median of 6.1 days.",
    stages: [
      { stage: "Applied", median_days: 2.7, stays: 100 },
      { stage: "Onsite", median_days: 6.1, stays: 16 },
      { stage: "Offer", median_days: null, stays: 0 },
    ],
  },
  days_open_vs_target: {
    metric: "days_open_vs_target",
    as_of: "2026-11-09T17:00:00Z",
    takeaway: "1 of 2 open jobs past target; JOB-1 is furthest over.",
    jobs: [
      { job_id: "JOB-1", title: "Senior Controls Engineer", days_open: 125, target_days: 60, days_over_target: 65, over_target: true },
      { job_id: "JOB-3", title: "People Operations Partner", days_open: 30, target_days: 40, days_over_target: -10, over_target: false },
    ],
  },
} as unknown as DashboardResponse;

describe("chart table views", () => {
  it("shows the takeaway and switches to a table with the API's values", async () => {
    render(<TimeInStageChart data={DATA} />);
    expect(screen.getByText(DATA.time_in_stage.takeaway)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    await userEvent.click(screen.getByRole("switch", { name: "View as table" }));
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows.map((r) => r.textContent)).toEqual([
      "StageMedian daysFinished stays",
      "Applied2.7100",
      "Onsite6.116",
      "OfferNo data0",
    ]);
  });

  it("labels jobs over target in words in the table", async () => {
    render(<DaysOpenChart data={DATA} />);
    await userEvent.click(screen.getByRole("switch", { name: "View as table" }));
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Over target")).toBeTruthy();
    expect(table.getByText("On track")).toBeTruthy();
  });

  it("links Ask about this to the ask page with the question in the URL", () => {
    render(<DaysOpenChart data={DATA} />);
    const link = screen.getByRole("link", { name: "Ask about this" });
    expect(link.getAttribute("href")).toBe(`/ask?q=${encodeURIComponent("Which roles are behind target?")}`);
  });
});
