"use client";

/**
 * Pipeline funnel by stage: how many applications reached each stage, with rejections and
 * withdrawals as their own bars. Choosing a stage, by clicking its bar or its button, lists
 * the candidates currently in that stage.
 */

import { Button } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard } from "@/components/ChartCard";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import { show } from "@/lib/format";
import type { DashboardResponse } from "@/lib/types";

export function FunnelChart({ data }: { data: DashboardResponse }) {
  const { funnel, stage_candidates } = data;
  const [stage, setStage] = useState<string | null>(null);
  const picked = stage ? (stage_candidates[stage] ?? []) : [];
  return (
    <ChartCard
      anchor="funnel"
      title="Pipeline funnel"
      takeaway={funnel.takeaway}
      question="Where is the pipeline losing candidates, and why?"
      empty={funnel.stages[0]?.reached === 0}
      table={{
        columns: ["Stage", "Reached", "In stage now", "Rejected", "Withdrawn", "Conversion from previous"],
        rows: funnel.stages.map((s) => [s.stage, s.reached, s.in_stage, s.rejected, s.withdrawn, show(s.conversion_pct, "%")]),
      }}
      chart={
        <ResponsiveContainer>
        <BarChart data={funnel.stages} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="stage" {...AXIS} interval={0} fontSize={11} angle={-25} textAnchor="end" height={56} />
          <YAxis {...AXIS} allowDecimals={false} />
          <Tooltip {...TOOLTIP} />
          <Legend />
          <Bar dataKey="reached" name="Reached" fill={COLORS.main} cursor="pointer" onClick={(d) => setStage(String(d.payload?.stage ?? ""))} {...STILL} />
          <Bar dataKey="rejected" name="Rejected" fill={COLORS.second} {...STILL} />
          <Bar dataKey="withdrawn" name="Withdrawn" fill={COLORS.third} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      }
    >
      <p className="label-small" style={{ marginTop: 8 }}>
        Show who is in a stage now
      </p>
      <div className="card-actions" aria-label="Show who is in a stage now">
        {funnel.stages
          .filter((s) => s.in_stage > 0)
          .map((s) => (
            <Button key={s.stage} size="sm" variant={stage === s.stage ? "primary" : "secondary"} onClick={() => setStage(s.stage)} aria-pressed={stage === s.stage}>
              {s.stage}: {s.in_stage} now
            </Button>
          ))}
      </div>
      {stage && (
        <div aria-live="polite">
          <h3>Candidates in {stage}</h3>
          {picked.length === 0 ? (
            <p className="muted">No active candidates are in this stage.</p>
          ) : (
            <ul className="chips list-plain">
              {picked.map((c) => (
                <li key={c.application_id}>
                  <Link className="chip" href={`/jobs/${c.job_id}`}>
                    {c.application_id} {c.full_name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </ChartCard>
  );
}
