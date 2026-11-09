"use client";

/**
 * The full evidence for one application from GET /api/candidates/{id}, using the same
 * component as the Ask page's drawer. An ID outside the user's scope comes back as 404 and
 * shows the not-found page.
 */

import { notFound, useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { EvidenceBody } from "@/components/EvidenceView";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getCandidate } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

export default function CandidatePage() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const result = useLoad(() => getCandidate(applicationId), applicationId);
  if (result.state === "not_found") notFound();
  return (
    <AppShell>
      {result.state === "loading" && <LoadingSkeleton blocks={3} label="Loading the candidate" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {result.state === "ready" && (
        <div className="fade-in">
          <div className="page-head">
            <div>
              <p className="label-small">Candidate evidence</p>
              <h1>{result.data.full_name}</h1>
              <p>Contact details are masked. Text marked Candidate-provided was written by the candidate.</p>
            </div>
          </div>
          <EvidenceBody evidence={result.data} />
        </div>
      )}
    </AppShell>
  );
}
