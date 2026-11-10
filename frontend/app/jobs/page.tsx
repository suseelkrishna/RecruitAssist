"use client";

/**
 * The jobs list from GET /api/jobs, with team, recruiter, status, and over-target filters
 * kept in the URL query. Filtering only hides rows; every number in a row comes from the API.
 * The table shows ten jobs at a time and goes back to the first page when a filter changes.
 */

import { Checkbox, DataTable, Field, Select } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { JobStatus, TargetStatus } from "@/components/JobStatus";
import { MiniFunnel } from "@/components/MiniFunnel";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { PageControls, usePaged } from "@/components/Paged";
import { getJobs } from "@/lib/api";
import { useQueryFilters } from "@/lib/query";
import type { BoardJob } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

const FILTERS = ["team", "recruiter", "status", "over"] as const;

/** True when the job passes the chosen filters. */
function matches(job: BoardJob, f: Record<(typeof FILTERS)[number], string>): boolean {
  if (f.team && job.team_id !== f.team) return false;
  if (f.recruiter && job.recruiter_user_id !== f.recruiter) return false;
  if (f.status === "open" && job.status !== "open") return false;
  if (f.status === "closed" && job.status === "open") return false;
  if (f.over === "1" && !job.over_target) return false;
  return true;
}

/** The filtered jobs as a table, ten at a time, or an empty state. */
function JobsTable({ jobs, rows, filterKey }: { jobs: BoardJob[]; rows: BoardJob[]; filterKey: string }) {
  const paged = usePaged(rows, 10, filterKey);
  if (jobs.length === 0) return <Empty title="No jobs in your scope" description="Jobs assigned to you or your teams will appear here." />;
  if (rows.length === 0) return <Empty title="No jobs match these filters" description="Clear a filter to see more jobs." />;
  return (
    <>
      <DataTable
        caption="Jobs in your scope"
        columns={["Job", "Recruiter", "Hiring manager", "Days open / target", "Active", "Funnel", "Overdue", "Status"]}
        rows={paged.rows.map((j) => [
          <span key="job">
            <Link className="ff-link" href={`/jobs/${j.job_id}`}>
              {j.title}
            </Link>
            <span className="cell-sub">
              <span className="mono">{j.req_code}</span>, {j.team}
            </span>
          </span>,
          j.recruiter_name ?? "Unassigned",
          j.hiring_manager,
          <span key="days">
            {j.days_open} / {j.target_fill_days}
            <span className="cell-sub">
              <TargetStatus overTarget={j.over_target} open={j.status === "open"} />
            </span>
          </span>,
          j.active_applications,
          <MiniFunnel key="funnel" stages={j.active_by_stage} />,
          j.overdue_tasks,
          <JobStatus key="status" status={j.status} />,
        ])}
      />
      <PageControls paged={paged} noun="jobs" label="Jobs, pages" />
    </>
  );
}

function Jobs() {
  const [values, set, clear] = useQueryFilters(FILTERS);
  const result = useLoad(getJobs, "jobs");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Jobs</h1>
        </div>
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={1} label="Loading jobs" />}
      {(result.state === "error" || result.state === "not_found") && (
        <ErrorState message={result.state === "error" ? result.message : "Jobs could not be loaded."} onRetry={result.reload} />
      )}
      {result.state === "ready" && (
        <div className="fade-in">
          <div className="filters" role="group" aria-label="Job filters">
            <Field label="Team">
              <Select value={values.team} onChange={(e) => set("team", e.target.value)} options={[{ label: "All teams", value: "" }, ...result.data.teams.map((t) => ({ label: t.name, value: t.team_id }))]} />
            </Field>
            <Field label="Recruiter">
              <Select value={values.recruiter} onChange={(e) => set("recruiter", e.target.value)} options={[{ label: "All recruiters", value: "" }, ...result.data.recruiters.map((r) => ({ label: r.name, value: r.user_id }))]} />
            </Field>
            <Field label="Status">
              <Select value={values.status} onChange={(e) => set("status", e.target.value)} options={[{ label: "Open and closed", value: "" }, { label: "Open", value: "open" }, { label: "Closed", value: "closed" }]} />
            </Field>
            <Checkbox label="Over target only" checked={values.over === "1"} onCheckedChange={(c) => set("over", c === true ? "1" : "")} />
            {FILTERS.some((f) => values[f]) && (
              <button type="button" className="link-button filters-clear" onClick={clear}>
                Clear filters
              </button>
            )}
          </div>
          <JobsTable jobs={result.data.jobs} rows={result.data.jobs.filter((j) => matches(j, values))} filterKey={FILTERS.map((f) => values[f]).join("|")} />
        </div>
      )}
    </>
  );
}

export default function JobsPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingSkeleton blocks={1} label="Loading jobs" />}>
        <Jobs />
      </Suspense>
    </AppShell>
  );
}
