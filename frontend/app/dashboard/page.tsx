"use client";

/**
 * The dashboard: filters, six headline numbers, and eight charts, all from one call to
 * GET /api/dashboard with the filters as query parameters. The filters live in the URL.
 */

import { Field, Select } from "@suseelkrishna/fieryfusion-react";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { ApplicantsChart } from "@/components/charts/ApplicantsChart";
import { DaysOpenChart } from "@/components/charts/DaysOpenChart";
import { FunnelChart } from "@/components/charts/FunnelChart";
import { OfferAcceptanceChart } from "@/components/charts/OfferAcceptanceChart";
import { RecruiterLoadChart } from "@/components/charts/RecruiterLoadChart";
import { SourceQualityChart } from "@/components/charts/SourceQualityChart";
import { TimeInStageChart } from "@/components/charts/TimeInStageChart";
import { WithdrawalChart } from "@/components/charts/WithdrawalChart";
import { KpiTiles } from "@/components/KpiTiles";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getDashboard } from "@/lib/api";
import { useQueryFilters } from "@/lib/query";
import type { DashboardResponse } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

const FILTERS = ["team", "job", "recruiter", "days"] as const;

/** The filter bar. Choices come from the API's options, so a role only sees its own teams and jobs. */
function Filters({ data, values, set }: { data: DashboardResponse | null; values: Record<(typeof FILTERS)[number], string>; set: (name: (typeof FILTERS)[number], value: string) => void }) {
  const options = data?.options;
  return (
    <div className="filters" role="group" aria-label="Dashboard filters">
      <Field label="Team">
        <Select value={values.team} onChange={(e) => set("team", e.target.value)} options={[{ label: "All teams", value: "" }, ...(options?.teams ?? []).map((t) => ({ label: t.name, value: t.team_id }))]} />
      </Field>
      <Field label="Job">
        <Select value={values.job} onChange={(e) => set("job", e.target.value)} options={[{ label: "All jobs", value: "" }, ...(options?.jobs ?? []).map((j) => ({ label: `${j.job_id} ${j.title}`, value: j.job_id }))]} />
      </Field>
      {(options?.recruiters.length ?? 0) > 0 && (
        <Field label="Recruiter">
          <Select value={values.recruiter} onChange={(e) => set("recruiter", e.target.value)} options={[{ label: "All recruiters", value: "" }, ...(options?.recruiters ?? []).map((r) => ({ label: r.name, value: r.user_id }))]} />
        </Field>
      )}
      <Field label="Applied in">
        <Select value={values.days} onChange={(e) => set("days", e.target.value)} options={[{ label: "All time", value: "" }, ...(options?.range_days ?? [30, 90, 180]).map((d) => ({ label: `Last ${d} days`, value: String(d) }))]} />
      </Field>
    </div>
  );
}

function Dashboard() {
  const [values, set] = useQueryFilters(FILTERS);
  const key = FILTERS.map((f) => values[f]).join("|");
  const result = useLoad(() => getDashboard(values), key);
  if (result.state === "not_found") notFound();
  const data = result.state === "ready" ? result.data : null;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>Every number here comes from the database for the jobs in your scope.</p>
        </div>
      </div>
      <Filters data={data} values={values} set={set} />
      {result.state === "loading" && <LoadingSkeleton blocks={4} label="Loading the dashboard" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {data && (
        <div className="fade-in">
          <KpiTiles kpis={data.kpis} />
          <div className="grid grid-charts">
            <FunnelChart data={data} />
            <DaysOpenChart data={data} />
            <ApplicantsChart data={data} />
            <SourceQualityChart data={data} />
            <TimeInStageChart data={data} />
            <WithdrawalChart data={data} />
            {data.recruiter_load && <RecruiterLoadChart metric={data.recruiter_load} />}
            <OfferAcceptanceChart data={data} />
          </div>
        </div>
      )}
    </>
  );
}

export default function DashboardPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingSkeleton blocks={4} label="Loading the dashboard" />}>
        <Dashboard />
      </Suspense>
    </AppShell>
  );
}
