"use client";

/**
 * Quality from GET /api/quality: test counts, the access matrix result, the mutation check,
 * and the eval scoreboard per model, with the date and git commit they were measured at. These come
 * from report files the backend reads (evals/quality.json, written by evals/quality_snapshot.py);
 * a report that has not been produced yet shows "Not available" with the reason. Admin only:
 * other roles get the not-found page because the API answers 404.
 */

import { DataTable, Stack, StatusPill } from "@suseelkrishna/fieryfusion-react";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { isScoreboard, Scoreboard, scoreboardInfo } from "@/components/Scoreboard";
import { ReportCard } from "@/components/ReportCard";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getQuality } from "@/lib/api";
import { formatDateTime, words } from "@/lib/format";
import type { QualityResponse } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

/** Show a report value as the API gives it: a list of rows as a table, an object as labeled fields. */
function Value({ value, caption }: { value: unknown; caption: string }): ReactNode {
  if (value === null || value === undefined) return <span className="muted">No value</span>;
  if (Array.isArray(value)) {
    if (value.length > 0 && value.every((v) => v && typeof v === "object" && !Array.isArray(v))) {
      const columns = [...new Set(value.flatMap((v) => Object.keys(v as object)))];
      return (
        <DataTable
          caption={caption}
          columns={columns.map(words)}
          rows={value.map((row) => columns.map((c) => <Value key={c} value={(row as Record<string, unknown>)[c]} caption={c} />))}
        />
      );
    }
    return <span>{value.map(String).join(", ")}</span>;
  }
  if (typeof value === "object") {
    return (
      <dl className="kv">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{words(k)}</dt>
            <dd>
              <Value value={v} caption={k} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  if (typeof value === "boolean") return value ? <StatusPill tone="success">Pass</StatusPill> : <StatusPill tone="danger">Fail</StatusPill>;
  return <span>{String(value)}</span>;
}

type Mutation = {
  caught: number;
  total: number;
  ran_at: string;
  mutants: { id: string; file: string; what_it_breaks: string; caught: boolean }[];
};

/** True when the mutation block has the fields the mutation card shows. */
function isMutation(value: unknown): value is Mutation {
  return !!value && typeof value === "object" && Array.isArray((value as Mutation).mutants);
}

/** The mutation card body: how many planted bugs the tests caught, when, and one row per bug. */
function MutationResult({ mutation }: { mutation: Mutation }) {
  return (
    <Stack gap={12}>
      <p style={{ margin: 0 }}>
        <strong>
          {mutation.caught} of {mutation.total}
        </strong>{" "}
        planted bugs caught by the tests.
      </p>
      <p className="muted quality-meta">Ran {formatDateTime(mutation.ran_at)}.</p>
      <DataTable
        caption="Planted bugs"
        columns={["Bug", "What it breaks", "Result"]}
        rows={mutation.mutants.map((m) => [
          <span className="mono" key="id">
            {m.id}
          </span>,
          m.what_it_breaks,
          m.caught ? (
            <StatusPill key="r" tone="success">
              Caught
            </StatusPill>
          ) : (
            <StatusPill key="r" tone="danger">
              Not caught
            </StatusPill>
          ),
        ])}
      />
    </Stack>
  );
}

/** "Measured <date> at commit <hash>", noting uncommitted changes, or a note that nothing was measured. */
function measuredAt(data: QualityResponse): string {
  if (!data.generated_at) return "Test reports have not been produced yet.";
  const commit = data.git_commit ? ` at commit ${data.git_commit}${data.git_dirty ? " with uncommitted changes" : ""}` : "";
  return `Measured ${formatDateTime(data.generated_at)}${commit}.`;
}

export default function QualityPage() {
  const result = useLoad(getQuality, "quality");
  if (result.state === "not_found") notFound();
  const reason = (key: string) => (result.state === "ready" ? result.data.reasons[key] : undefined);
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <HeadingWithInfo as="h1" title="Quality" info="How the backend and the assistant are tested. These numbers come from report files produced by the test and eval scripts." />
          {result.state === "ready" && <p className="muted quality-meta">{measuredAt(result.data)}</p>}
        </div>
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={4} label="Loading quality" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {result.state === "ready" && (
        <Stack gap={16} className="fade-in">
          <p className="muted">The backend defines {result.data.tests_defined} test functions.</p>
          <div className="grid grid-2">
            <ReportCard title="Test results" value={result.data.tests} reason={reason("tests")}>
              <Value value={result.data.tests} caption="Test results" />
            </ReportCard>
            <ReportCard title="Access matrix" value={result.data.rbac} reason={reason("rbac")}>
              <Value value={result.data.rbac} caption="Access matrix" />
            </ReportCard>
          </div>
          <ReportCard title="Mutation check" value={result.data.mutation} reason={reason("mutation")}>
            {isMutation(result.data.mutation) ? (
              <MutationResult mutation={result.data.mutation} />
            ) : (
              <Value value={result.data.mutation} caption="Mutation check" />
            )}
          </ReportCard>
          <ReportCard
            title="Eval scoreboard by model"
            value={result.data.scoreboard}
            reason={reason("scoreboard")}
            info={isScoreboard(result.data.scoreboard) ? scoreboardInfo(result.data.scoreboard) : undefined}
          >
            {isScoreboard(result.data.scoreboard) ? (
              <Scoreboard report={result.data.scoreboard} />
            ) : (
              <Value value={result.data.scoreboard} caption="Eval scoreboard by model" />
            )}
          </ReportCard>
        </Stack>
      )}
    </AppShell>
  );
}
