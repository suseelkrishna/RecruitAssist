"use client";

/**
 * Source quality: the share of each source's applicants that reached Onsite, as one set of bars
 * on a single percent axis. Each bar's label carries the applicant count from the API, and the
 * table view adds hires and time to hire.
 */

import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import { show } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";

export function SourceQualityChart({ data }: { data: DashboardResponse }) {
  const { source_quality: metric } = data;
  const rows = metric.sources.map((s) => ({
    ...s,
    label: `${s.source} (${s.applicants})`,
    shown: s.onsite_rate_pct === null ? "" : `${s.onsite_rate_pct}%`,
  }));
  return (
    <ChartCard
      anchor="source-quality"
      title="Source quality"
      takeaway={metric.takeaway}
      info="Bars show the share of applicants who reached Onsite. The number in brackets is how many applied."
      question="Which sources bring the best candidates?"
      empty={metric.sources.length === 0}
      table={{
        columns: ["Source", "Applicants", "Reached Onsite", "Share reaching Onsite", "Hires", "Median days to hire"],
        rows: metric.sources.map((s) => [s.source, s.applicants, s.reached_onsite, show(s.onsite_rate_pct, "%"), s.hires, show(s.median_days_to_hire)]),
      }}
      chart={
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 24, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="label" {...AXIS} interval={0} fontSize={11} />
            <YAxis {...AXIS} unit="%" domain={[0, 100]} />
            <Tooltip {...TOOLTIP} />
            <Bar dataKey="onsite_rate_pct" name="Share of applicants reaching Onsite (%)" fill={COLORS.main} {...STILL}>
              <LabelList dataKey="shown" position="top" fill={COLORS.ink} fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      }
    />
  );
}
