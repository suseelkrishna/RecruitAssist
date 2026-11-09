"use client";

/**
 * The catch-up view, the first page after picking a demo user. It greets the user by first
 * name, gives one line on what needs attention, and shows a few headline tiles from
 * GET /api/catch-up. Clicking a tile opens its detail in one panel below the tiles. The
 * dashboard data behind the charts loads only when a chart tile is opened, so nothing heavy
 * runs until someone asks for it.
 */

import { ButtonLink, Card } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { ApplicantsChart } from "@/components/charts/ApplicantsChart";
import { DaysOpenChart } from "@/components/charts/DaysOpenChart";
import { FunnelChart } from "@/components/charts/FunnelChart";
import { OfferAcceptanceChart } from "@/components/charts/OfferAcceptanceChart";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getCatchUp, getDashboard } from "@/lib/api";
import { show } from "@/lib/format";
import type { CatchUpResponse, CatchUpTile } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

type TileKey = CatchUpTile["key"];
type ChartKey = Exclude<TileKey, "overdue_tasks">;

/** The overdue tasks the API listed, most overdue first, with a link to the full task list. */
function OverduePanel({ data }: { data: CatchUpResponse }) {
  if (data.overdue_tasks.length === 0) {
    return <Empty title="Nothing overdue" description="Every open task in your scope is still on time." />;
  }
  return (
    <Card>
      <h2 className="chart-title">Most overdue tasks</h2>
      <ul className="catchup-tasks list-plain">
        {data.overdue_tasks.map((t) => (
          <li key={`${t.task_id ?? t.application_id}-${t.title}`}>
            <span className="catchup-task-title">{t.title}</span>
            <span className="muted">
              {t.task_id ? `${t.task_id}, ` : ""}
              {t.job_id}
              {t.owner_name ? `, ${t.owner_name}` : ""}, {show(t.days_overdue)} days overdue
            </span>
          </li>
        ))}
      </ul>
      <ButtonLink as={Link} href="/tasks" variant="secondary" size="sm">
        {data.overdue_more > 0 ? `See all tasks (${data.overdue_more} more overdue)` : "See all tasks"}
      </ButtonLink>
    </Card>
  );
}

/** One chart from the dashboard data. Loads that data once and keeps it while mounted. */
function ChartPanel({ open }: { open: ChartKey }) {
  const result = useLoad(() => getDashboard({}), "catch-up-dashboard");
  if (result.state === "loading") return <LoadingSkeleton blocks={1} label="Loading the chart" />;
  if (result.state !== "ready") {
    return <ErrorState message={result.state === "error" ? result.message : "The chart could not be loaded."} onRetry={result.reload} />;
  }
  const data = result.data;
  if (open === "jobs_past_target") return <DaysOpenChart data={data} />;
  if (open === "active_candidates") return <FunnelChart data={data} />;
  if (open === "new_applicants_7d") return <ApplicantsChart data={data} />;
  return <OfferAcceptanceChart data={data} />;
}

/** The catch-up page body: greeting, summary line, tiles, the open tile's panel, and the full dashboard link. */
export function CatchUp() {
  const result = useLoad(getCatchUp, "catch-up");
  const [open, setOpen] = useState<TileKey | null>(null);
  const tileRefs = useRef<Partial<Record<TileKey, HTMLButtonElement | null>>>({});
  const panelId = useId();

  /** Open a tile's panel, or close it when it is already open. */
  function toggle(key: TileKey) {
    setOpen((current) => (current === key ? null : key));
  }

  /** Escape inside the panel closes it and puts focus back on its tile. */
  function onPanelKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Escape" || !open) return;
    tileRefs.current[open]?.focus();
    setOpen(null);
  }

  if (result.state === "loading") return <LoadingSkeleton blocks={2} label="Loading your catch-up" />;
  if (result.state !== "ready") {
    return <ErrorState message={result.state === "error" ? result.message : "Your catch-up could not be loaded."} onRetry={result.reload} />;
  }
  const data = result.data;
  const openTile = data.tiles.find((t) => t.key === open);

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h1>Hi {data.first_name}</h1>
          <p className="catchup-summary">{data.summary}</p>
        </div>
        <ButtonLink as={Link} href="/dashboard?view=full" variant="secondary">
          View full dashboard
        </ButtonLink>
      </div>

      <section aria-label="What needs attention">
        <ul className="grid catchup-tiles list-plain">
          {data.tiles.map((t) => (
            <li key={t.key}>
              <button
                type="button"
                ref={(el) => {
                  tileRefs.current[t.key] = el;
                }}
                className="catchup-tile"
                aria-expanded={open === t.key}
                aria-controls={panelId}
                onClick={() => toggle(t.key)}
              >
                <span className="kpi-label">{t.label}</span>
                <span className="kpi-value">{show(t.value)}</span>
                <span className="catchup-note">{t.note}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div id={panelId} className="catchup-panel" role="region" aria-label={openTile ? openTile.label : "Tile details"} onKeyDown={onPanelKey}>
        {open === "overdue_tasks" && <OverduePanel data={data} />}
        {open && open !== "overdue_tasks" && <ChartPanel open={open} />}
        {!open && <p className="muted catchup-hint">Choose a tile to see the chart or list behind it.</p>}
      </div>
    </div>
  );
}
