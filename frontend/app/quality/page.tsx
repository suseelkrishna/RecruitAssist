"use client";

/**
 * Quality from GET /api/quality: test counts, the mutation score, the access matrix result,
 * and the eval scoreboard per model, with the date they were produced. These come from report
 * files the backend reads; a report that has not been produced yet shows as not run.
 */

import { Card, DataTable, Stack, StatusPill } from "@suseelkrishna/fieryfusion-react";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { isScoreboard, Scoreboard } from "@/components/Scoreboard";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getQuality } from "@/lib/api";
import { formatDateTime, words } from "@/lib/format";
import { useLoad } from "@/lib/useLoad";

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

/** One report section, or a note that the report has not been produced yet. */
function Section({ title, value, missing, children }: { title: string; value: unknown; missing: string | undefined; children?: ReactNode }) {
  return (
    <Card title={title} className="quality-card">
      {value === null || value === undefined ? (
        <StatusPill tone="info">Not run yet</StatusPill>
      ) : (
        (children ?? <Value value={value} caption={title} />)
      )}
      {missing && (
        <p className="muted" style={{ marginBottom: 0 }}>
          This report has not been produced yet.
        </p>
      )}
    </Card>
  );
}

export default function QualityPage() {
  const result = useLoad(getQuality, "quality");
  const missingFor = (key: string) => (result.state === "ready" ? result.data.missing.find((m) => m.startsWith(key)) : undefined);
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <h1>Quality</h1>
          <p>How the backend and the assistant are tested.</p>
        </div>
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={4} label="Loading quality" />}
      {(result.state === "error" || result.state === "not_found") && (
        <ErrorState message={result.state === "error" ? result.message : "Quality could not be loaded."} onRetry={result.reload} />
      )}
      {result.state === "ready" && (
        <Stack gap={16} className="fade-in">
          <p className="muted">
            {result.data.generated_at ? `Test reports produced ${formatDateTime(result.data.generated_at)}.` : "Test reports have not been produced yet."}{" "}
            The backend defines {result.data.tests_defined} test functions.
          </p>
          <div className="grid grid-2">
            <Section title="Test results" value={result.data.tests} missing={missingFor("tests")} />
            <Section title="Mutation score" value={result.data.mutation_score} missing={missingFor("mutation_score")} />
            <Section title="Access matrix" value={result.data.rbac} missing={missingFor("rbac")} />
          </div>
          <Section title="Eval scoreboard by model" value={result.data.scoreboard} missing={missingFor("scoreboard")}>
            {isScoreboard(result.data.scoreboard) ? <Scoreboard report={result.data.scoreboard} /> : undefined}
          </Section>
        </Stack>
      )}
    </AppShell>
  );
}
