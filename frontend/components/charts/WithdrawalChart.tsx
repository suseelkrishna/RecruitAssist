"use client";

/** Why candidates withdrew, most common reason first. */

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import type { DashboardResponse } from "@/lib/types";

export function WithdrawalChart({ data }: { data: DashboardResponse }) {
  const { withdrawal_reasons: metric } = data;
  return (
    <ChartCard
      anchor="withdrawals"
      title="Withdrawals by reason"
      takeaway={metric.takeaway}
      question="Why are candidates withdrawing?"
      empty={metric.reasons.length === 0}
      table={{
        columns: ["Reason", "Withdrawals", "Applications"],
        rows: metric.reasons.map((r) => [r.reason, r.count, r.evidence.join(", ")]),
      }}
      chart={
      <ResponsiveContainer>
        <BarChart data={metric.reasons} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} horizontal={false} />
          <XAxis type="number" {...AXIS} allowDecimals={false} />
          <YAxis type="category" dataKey="reason" {...AXIS} width={170} fontSize={11} />
          <Tooltip {...TOOLTIP} />
          <Bar dataKey="count" name="Withdrawals" fill={COLORS.main} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      }
    />
  );
}
