"use client";

/** Days open against the target for each open job, as horizontal bars with an "Over target" label. */

import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import type { DashboardResponse } from "@/lib/types";

export function DaysOpenChart({ data }: { data: DashboardResponse }) {
  const { days_open_vs_target: metric } = data;
  const rows = metric.jobs.map((j) => ({ ...j, label: `${j.job_id} ${j.title}`, flag: j.over_target ? "Over target" : "" }));
  return (
    <ChartCard
      anchor="days-open"
      title="Days open vs target"
      takeaway={metric.takeaway}
      question="Which roles are behind target?"
      empty={rows.length === 0}
      table={{
        columns: ["Job", "Days open", "Target days", "Days over target", "Status"],
        rows: metric.jobs.map((j) => [`${j.job_id} ${j.title}`, j.days_open, j.target_days, j.days_over_target, j.over_target ? "Over target" : "On track"]),
      }}
      chart={
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 96, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} horizontal={false} />
          <XAxis type="number" {...AXIS} />
          <YAxis type="category" dataKey="title" {...AXIS} width={150} fontSize={11} />
          <Tooltip {...TOOLTIP} />
          <Legend />
          <Bar dataKey="days_open" name="Days open" fill={COLORS.main} {...STILL}>
            <LabelList dataKey="flag" position="right" fill={COLORS.ink} fontSize={12} />
          </Bar>
          <Bar dataKey="target_days" name="Target days" fill={COLORS.third} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      }
    />
  );
}
