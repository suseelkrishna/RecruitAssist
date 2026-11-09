/**
 * The eval scoreboard from evals/scoreboard.json, as one row per model and effort setting with
 * the numbers a reader compares: pass rates, speed, cost, and the judge's scores. The default
 * setting is marked in words. Every value is shown as the report gives it.
 */

import { DataTable, StatusPill } from "@suseelkrishna/fieryfusion-react";
import { formatDateTime, show } from "@/lib/format";

export type ScoreboardSetting = {
  model: string;
  effort: string;
  runs: number;
  passed: number;
  pass_rate_pct: number | null;
  verified_pass_rate_pct: number | null;
  latency_p50_s: number | null;
  latency_p95_s: number | null;
  cost_per_question_usd: number | null;
  llm_judge?: { faithfulness?: number | null; clarity?: number | null } | null;
};

export type ScoreboardReport = {
  generated_at?: string;
  questions?: number;
  repeats?: number;
  default?: { model: string; effort: string };
  default_rule?: string;
  settings?: ScoreboardSetting[];
  total_cost_usd?: number;
};

/** True when the value looks like a scoreboard this component knows how to show. */
export function isScoreboard(value: unknown): value is ScoreboardReport {
  return !!value && typeof value === "object" && Array.isArray((value as ScoreboardReport).settings);
}

/** How to read the scoreboard and how the default model is chosen, for the InfoTip after its title. */
export function scoreboardInfo(report: ScoreboardReport): string {
  const repeats =
    report.questions !== undefined && report.repeats !== undefined
      ? `${report.questions} questions, each asked ${report.repeats} times per setting. `
      : "";
  return `${repeats}Judge scores run from 1 to 5.${report.default_rule ? ` How the default is chosen: ${report.default_rule}` : ""}`;
}

export function Scoreboard({ report }: { report: ScoreboardReport }) {
  const settings = report.settings ?? [];
  const isDefault = (s: ScoreboardSetting) => report.default?.model === s.model && report.default?.effort === s.effort;
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>
        Run {formatDateTime(report.generated_at)}.
        {report.default ? ` The app uses ${report.default.model} at ${report.default.effort} effort.` : ""}
      </p>
      <DataTable
        caption="Eval results by model and effort"
        columns={["Model", "Effort", "Passed", "Pass rate", "Verified pass rate", "Typical answer time", "Cost per question", "Judge, faithful / clear"]}
        rows={settings.map((s) => [
          <span key="model">
            {s.model}
            {isDefault(s) && (
              <span className="cell-sub">
                <StatusPill tone="success">Default</StatusPill>
              </span>
            )}
          </span>,
          s.effort,
          `${s.passed} of ${s.runs}`,
          show(s.pass_rate_pct, "%"),
          show(s.verified_pass_rate_pct, "%"),
          s.latency_p50_s === null || s.latency_p50_s === undefined ? "No data" : `${s.latency_p50_s} s (95% within ${show(s.latency_p95_s)} s)`,
          s.cost_per_question_usd === null || s.cost_per_question_usd === undefined ? "No data" : `${s.cost_per_question_usd} USD`,
          s.llm_judge ? `${show(s.llm_judge.faithfulness)} / ${show(s.llm_judge.clarity)}` : "Not judged",
        ])}
      />
    </div>
  );
}
