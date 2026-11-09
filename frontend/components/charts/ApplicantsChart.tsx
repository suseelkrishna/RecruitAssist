"use client";

/** New applicants per week, as one total or split by source. */

import { Switch } from "@suseelkrishna/fieryfusion-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, SERIES, STILL, TOOLTIP } from "@/components/charts/theme";
import { formatDate } from "@/lib/format";
import type { DashboardResponse, WeekRow } from "@/lib/types";

/** Rows of { week_start, [source]: applicants } for stacked bars. Values are copied, not added. */
function bySourceRows(weeks: WeekRow[]): { rows: Record<string, string | number>[]; sources: string[] } {
  const sources = [...new Set(weeks.map((w) => w.source ?? ""))].sort();
  const rows = new Map<string, Record<string, string | number>>();
  for (const w of weeks) {
    const row = rows.get(w.week_start) ?? { week_start: w.week_start };
    row[w.source ?? ""] = w.applicants;
    rows.set(w.week_start, row);
  }
  return { rows: [...rows.values()], sources };
}

export function ApplicantsChart({ data }: { data: DashboardResponse }) {
  const [split, setSplit] = useState(false);
  const total = data.applicants_total;
  const split_ = bySourceRows(data.applicants_over_time.weeks);
  return (
    <ChartCard
      anchor="applicants"
      title="Applicants per week"
      takeaway={total.takeaway}
      question="How has the number of new applicants changed week by week?"
      empty={total.weeks.length === 0}
      table={
        split
          ? {
              columns: ["Week starting", "Source", "Applicants"],
              rows: data.applicants_over_time.weeks.map((w) => [formatDate(w.week_start), w.source ?? "", w.applicants]),
            }
          : { columns: ["Week starting", "Applicants"], rows: total.weeks.map((w) => [formatDate(w.week_start), w.applicants]) }
      }
      controls={<Switch label="Split by source" checked={split} onCheckedChange={setSplit} />}
      chart={
      <ResponsiveContainer>
        {split ? (
          <BarChart data={split_.rows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="week_start" {...AXIS} tickFormatter={formatDate} />
            <YAxis {...AXIS} allowDecimals={false} />
            <Tooltip {...TOOLTIP} />
            <Legend />
            {split_.sources.map((s, i) => (
              <Bar key={s} dataKey={s} name={s} stackId="source" fill={SERIES[i % SERIES.length]} {...STILL} />
            ))}
          </BarChart>
        ) : (
          <BarChart data={total.weeks} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="week_start" {...AXIS} tickFormatter={formatDate} />
            <YAxis {...AXIS} allowDecimals={false} />
            <Tooltip {...TOOLTIP} />
            <Bar dataKey="applicants" name="Applicants" fill={COLORS.main} {...STILL} />
          </BarChart>
        )}
      </ResponsiveContainer>
      }
    />
  );
}
