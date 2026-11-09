"use client";

/**
 * The change log from GET /api/changes, newest first: reassignments and questions asked.
 * Question entries show only a short hash of the question, the tools used, the record IDs
 * touched, and the verifier result; no candidate text is stored. The log is append-only, so
 * there are no edit or delete controls. HR Users get the not-found page.
 */

import { DataTable, SegmentedControl, StatusPill } from "@suseelkrishna/fieryfusion-react";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { CitationChip } from "@/components/CitationChip";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getChanges } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useQueryFilters } from "@/lib/query";
import { ROLE_LABELS } from "@/lib/roles";
import type { ChangeEntry } from "@/lib/types";
import { toolName } from "@/lib/tools";
import { useLoad } from "@/lib/useLoad";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

const KINDS = { All: "", Reassignments: "reassignment", Questions: "ask" } as const;
type KindLabel = keyof typeof KINDS;

/** The details column: the reason for a reassignment, or tools, records, and verifier for a question. */
function Details({ entry }: { entry: ChangeEntry }) {
  if (entry.type === "reassignment") return <span>{entry.reason ? `Reason: ${entry.reason}` : "No reason given"}</span>;
  return (
    <div style={{ maxWidth: 380 }}>
      <div>
        {entry.verified ? <StatusPill tone="success">Verified</StatusPill> : <StatusPill tone="warning">Needs review</StatusPill>}{" "}
        {entry.source === "recording" && <span className="muted">Recorded answer</span>}
      </div>
      <div className="muted">Data looked up: {(entry.tools ?? []).map(toolName).join(", ") || "None"}</div>
      {(entry.record_ids ?? []).length > 0 && (
        <details className="records">
          <summary>Show records</summary>
          <span className="chips">
            {(entry.record_ids ?? []).map((id) => (
              <CitationChip key={id} id={id} />
            ))}
          </span>
        </details>
      )}
    </div>
  );
}

function Changes() {
  const [values, set] = useQueryFilters(["kind"] as const);
  const result = useLoad(getChanges, "changes");
  if (result.state === "not_found") notFound();
  const label = (Object.keys(KINDS) as KindLabel[]).find((k) => KINDS[k] === values.kind) ?? "All";

  return (
    <>
      <div className="page-head">
        <div>
          <HeadingWithInfo as="h1" title="Changes" info="An append-only log of reassignments and questions asked. Entries cannot be edited or deleted." />
        </div>
        <SegmentedControl label="Show" options={Object.keys(KINDS)} value={label} onChange={(v) => set("kind", KINDS[v as KindLabel])} />
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={1} label="Loading the change log" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {result.state === "ready" &&
        (() => {
          const rows = result.data.changes.filter((c) => !values.kind || c.type === values.kind);
          if (rows.length === 0)
            return (
              <Empty
                title="No entries yet"
                description="Reassignments and questions asked in your scope appear here."
              />
            );
          return (
            <DataTable
              caption="Change log, newest first"
              columns={["When", "Who", "Role", "Kind", "What", "Details"]}
              rows={rows.map((c) => [
                formatDateTime(c.at),
                c.user_name ?? c.user_id,
                c.user_role ? ROLE_LABELS[c.user_role] : "",
                c.type === "reassignment" ? "Reassignment" : "Question asked",
                <span key="what">
                  {c.type === "ask" ? (
                    <>
                      Question (text not stored)
                      <span className="cell-sub">
                        Reference <span className="mono">{c.question_hash}</span>
                      </span>
                    </>
                  ) : (
                    c.summary
                  )}
                </span>,
                <Details key="details" entry={c} />,
              ])}
            />
          );
        })()}
    </>
  );
}

export default function ChangesPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingSkeleton blocks={1} label="Loading the change log" />}>
        <Changes />
      </Suspense>
    </AppShell>
  );
}
