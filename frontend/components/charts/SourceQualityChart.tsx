"use client";

/** Source quality: applicants from each source, and the share of them that reached Onsite. */

import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import { show } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";

export function SourceQualityChart({ data }: { data: DashboardResponse }) {
  const { source_quality: metric } = data;
  return (
    <ChartCard
      anchor="source-quality"
      title="Source quality"
      takeaway={metric.takeaway}
      question="Which sources bring the best candidates?"
      empty={metric.sources.length === 0}
      table={{
        columns: ["Source", "Applicants", "Reached Onsite", "Share reaching Onsite", "Hires", "Median days to hire"],
        rows: metric.sources.map((s) => [s.source, s.applicants, s.reached_onsite, show(s.onsite_rate_pct, "%"), s.hires, show(s.median_days_to_hire)]),
      }}
      chart={
      <ResponsiveContainer>
        <ComposedChart data={metric.sources} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="source" {...AXIS} />
          <YAxis yAxisId="count" {...AXIS} allowDecimals={false} />
          <YAxis yAxisId="pct" orientation="right" {...AXIS} unit="%" domain={[0, 100]} />
          <Tooltip {...TOOLTIP} />
          <Legend />
          <Bar yAxisId="count" dataKey="applicants" name="Applicants" fill={COLORS.main} {...STILL} />
          <Line yAxisId="pct" dataKey="onsite_rate_pct" name="Share reaching Onsite (%)" stroke={COLORS.second} strokeWidth={2} dot={{ r: 4 }} {...STILL} />
        </ComposedChart>
      </ResponsiveContainer>
      }
    />
  );
}
