"use client";

/**
 * Offer acceptance: the acceptance rate of decided offers as a bar, and the applications
 * behind each outcome. The rate and counts come from the API; nothing is added up here.
 */

import { Progress } from "@suseelkrishna/fieryfusion-react";
import { ChartCard } from "@/components/ChartCard";
import type { DashboardResponse } from "@/lib/types";

export function OfferAcceptanceChart({ data }: { data: DashboardResponse }) {
  const { offer_acceptance: metric } = data;
  const outcomes: [string, string[]][] = [
    ["Accepted", metric.accepted],
    ["Declined", metric.declined],
    ["Withdrawn", metric.withdrawn],
    ["Pending", metric.pending],
  ];
  return (
    <ChartCard
      anchor="offers"
      title="Offer acceptance"
      takeaway={metric.takeaway}
      question="How many offers have been accepted, declined, or are still pending?"
      empty={metric.offers === 0}
      table={{ columns: ["Outcome", "Applications"], rows: outcomes.map(([label, ids]) => [label, ids.join(", ") || "None"]) }}
    >
      {metric.acceptance_rate_pct === null ? (
        <p className="muted">No offers have been decided yet.</p>
      ) : (
        <Progress value={metric.acceptance_rate_pct} label="Acceptance rate of decided offers" />
      )}
      <dl className="kv" style={{ marginTop: 16 }}>
        {outcomes.map(([label, ids]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt>{label}</dt>
            <dd className="mono">{ids.join(", ") || "None"}</dd>
          </div>
        ))}
      </dl>
    </ChartCard>
  );
}
