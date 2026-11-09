"use client";

/** Recruiter load: active candidates and overdue tasks per recruiter. Admin and HR Manager only. */

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import type { DashboardResponse } from "@/lib/types";

export function RecruiterLoadChart({ metric }: { metric: NonNullable<DashboardResponse["recruiter_load"]> }) {
  return (
    <ChartCard
      anchor="recruiter-load"
      title="Recruiter load"
      takeaway={metric.takeaway}
      question="Which recruiter is overloaded?"
      empty={metric.recruiters.length === 0}
      table={{
        columns: ["Recruiter", "Open jobs", "Active candidates", "Overdue tasks", "Jobs"],
        rows: metric.recruiters.map((r) => [r.name, r.open_jobs, r.active_candidates, r.overdue_tasks, r.job_ids.join(", ")]),
      }}
      chart={
      <ResponsiveContainer>
        <BarChart data={metric.recruiters} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="name" {...AXIS} />
          <YAxis {...AXIS} allowDecimals={false} />
          <Tooltip {...TOOLTIP} />
          <Legend />
          <Bar dataKey="active_candidates" name="Active candidates" fill={COLORS.main} {...STILL} />
          <Bar dataKey="overdue_tasks" name="Overdue tasks" fill={COLORS.second} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      }
    />
  );
}
