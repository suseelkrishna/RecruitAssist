"use client";

/** The median number of days candidates spend in each stage. */

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import { show } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";

export function TimeInStageChart({ data }: { data: DashboardResponse }) {
  const { time_in_stage: metric } = data;
  return (
    <ChartCard
      anchor="time-in-stage"
      title="Median time in each stage"
      takeaway={metric.takeaway}
      question="Which stage do candidates wait in the longest?"
      empty={metric.stages.length === 0}
      table={{
        columns: ["Stage", "Median days", "Finished stays"],
        rows: metric.stages.map((s) => [s.stage, show(s.median_days), s.stays]),
      }}
      chart={
      <ResponsiveContainer>
        <BarChart data={metric.stages} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="stage" {...AXIS} interval={0} fontSize={11} angle={-25} textAnchor="end" height={56} />
          <YAxis {...AXIS} unit=" d" />
          <Tooltip {...TOOLTIP} />
          <Bar dataKey="median_days" name="Median days" fill={COLORS.main} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      }
    />
  );
}
