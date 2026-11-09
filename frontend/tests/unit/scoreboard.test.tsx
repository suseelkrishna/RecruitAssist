/** The eval scoreboard shows one compact row per setting, marks the default, and copies values unchanged. */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { isScoreboard, Scoreboard, type ScoreboardReport } from "@/components/Scoreboard";

const REPORT: ScoreboardReport = {
  generated_at: "2026-11-09T07:08:12Z",
  questions: 18,
  repeats: 3,
  default: { model: "claude-haiku-5-5", effort: "low" },
  default_rule: "Highest verified pass rate.",
  settings: [
    { model: "claude-haiku-5-5", effort: "low", runs: 54, passed: 51, pass_rate_pct: 94.4, verified_pass_rate_pct: 88.9,
      latency_p50_s: 6.0, latency_p95_s: 16.9, cost_per_question_usd: 0.0015, llm_judge: { faithfulness: 3.94, clarity: 3.78 } },
    { model: "claude-opus-5-5", effort: "medium", runs: 54, passed: 50, pass_rate_pct: 92.6, verified_pass_rate_pct: null,
      latency_p50_s: 11.1, latency_p95_s: 25.3, cost_per_question_usd: 0.0541, llm_judge: null },
  ],
};

describe("Scoreboard", () => {
  it("shows one row per setting with the report's values and marks only the default", () => {
    render(<Scoreboard report={REPORT} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("51 of 54");
    expect(rows[0].textContent).toContain("94.4%");
    expect(rows[0].textContent).toContain("Default");
    expect(rows[0].textContent).toContain("3.94 / 3.78");
    expect(rows[1].textContent).not.toContain("Default");
    expect(rows[1].textContent).toContain("No data");
    expect(rows[1].textContent).toContain("Not judged");
  });

  it("recognizes a scoreboard and rejects other shapes", () => {
    expect(isScoreboard(REPORT)).toBe(true);
    expect(isScoreboard({ settings: "x" })).toBe(false);
    expect(isScoreboard(null)).toBe(false);
  });
});
