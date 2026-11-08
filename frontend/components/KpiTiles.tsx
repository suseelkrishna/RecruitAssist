/** The six headline numbers at the top of the dashboard, exactly as the API returns them. */

import { Card } from "@suseelkrishna/fieryfusion-react";
import { show } from "@/lib/format";
import type { Kpis } from "@/lib/types";

export function KpiTiles({ kpis }: { kpis: Kpis }) {
  const tiles = [
    { label: "Open jobs", value: show(kpis.open_jobs) },
    { label: "Active candidates", value: show(kpis.active_candidates) },
    { label: "New applicants, last 7 days", value: show(kpis.new_applicants_7d) },
    { label: "Offers out", value: show(kpis.offers_out) },
    { label: "Median time to fill", value: kpis.median_days_to_fill === null ? "No filled roles" : `${kpis.median_days_to_fill} days` },
    { label: "Overdue tasks", value: show(kpis.overdue_tasks) },
  ];
  return (
    <section aria-label="Headline numbers">
      <ul className="grid grid-kpis list-plain">
        {tiles.map((t) => (
          <li key={t.label}>
            <Card>
              <p className="kpi-label">{t.label}</p>
              <p className="kpi-value">{t.value}</p>
            </Card>
          </li>
        ))}
      </ul>
      <p className="takeaway">{kpis.takeaway}</p>
    </section>
  );
}
