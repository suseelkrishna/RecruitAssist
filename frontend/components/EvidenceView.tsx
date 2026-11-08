"use client";

/**
 * The evidence for one application from GET /api/candidates/{id}: the stage timeline, the CV
 * excerpt, scorecards, and emails. Free text written by the candidate is labeled
 * "Candidate-provided", and contact details arrive already masked by the backend.
 * The Ask page shows this in a drawer; the candidate page shows it on its own.
 */

import { Badge, Card, Skeleton, Stack } from "@suseelkrishna/fieryfusion-react";
import { ErrorState } from "@/components/PageStates";
import { getCandidate } from "@/lib/api";
import { formatDateTime, words } from "@/lib/format";
import type { Evidence } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

/** A block of untrusted free text with a label saying who wrote it. */
function FreeText({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="label-small">{label}</p>
      <p className="untrusted">{text}</p>
    </div>
  );
}

/** The evidence sections for a loaded application. */
export function EvidenceBody({ evidence }: { evidence: Evidence }) {
  const history = evidence.history;
  return (
    <Stack gap={20}>
      <dl className="kv">
        <dt>Application</dt>
        <dd className="mono">{evidence.application_id}</dd>
        <dt>Job</dt>
        <dd className="mono">{evidence.job_id}</dd>
        <dt>Current title</dt>
        <dd>{evidence.current_title}</dd>
        <dt>Stage</dt>
        <dd>
          {evidence.current_stage} <Badge tone="neutral">{words(evidence.status)}</Badge>
        </dd>
        <dt>Source</dt>
        <dd>{evidence.source}</dd>
        <dt>Email</dt>
        <dd>{evidence.contact.email}</dd>
        <dt>Phone</dt>
        <dd>{evidence.contact.phone}</dd>
      </dl>

      {history && (
        <section aria-label="Stage timeline">
          <h3>Stage timeline</h3>
          <ol className="list-plain">
            {history.stage_events.map((e) => (
              <li key={e.event_id}>
                <strong>{e.stage}</strong> <span className="mono muted">{e.event_id}</span>
                <br />
                <span className="muted">
                  Entered {formatDateTime(e.entered_at)}
                  {e.exited_at ? `, left ${formatDateTime(e.exited_at)} (${words(e.exit_type ?? "")})` : ", still here"}
                </span>
              </li>
            ))}
          </ol>
          {history.outcome && (
            <p>
              Outcome: {words(history.outcome.status)}, {history.outcome.reason} ({formatDateTime(history.outcome.at)})
            </p>
          )}
        </section>
      )}

      {evidence.cv && (
        <section aria-label="CV excerpt">
          <h3>CV excerpt</h3>
          <FreeText label="Candidate-provided" text={evidence.cv.untrusted_text} />
        </section>
      )}

      {evidence.scorecards && (
        <section aria-label="Scorecards">
          <h3>Scorecards</h3>
          {evidence.scorecards.length === 0 ? (
            <p className="muted">No scorecards submitted yet.</p>
          ) : (
            <Stack gap={12}>
              {evidence.scorecards.map((s) => (
                <Card key={s.scorecard_id}>
                  <p>
                    <strong>{s.stage}</strong> by {s.interviewer} <span className="mono muted">{s.scorecard_id}</span>
                  </p>
                  <p>Overall: {words(s.overall)}</p>
                  <dl className="kv">
                    {Object.entries(s.ratings).map(([skill, rating]) => (
                      <div key={skill} style={{ display: "contents" }}>
                        <dt>{skill}</dt>
                        <dd>{rating} of 4</dd>
                      </div>
                    ))}
                  </dl>
                  <FreeText label="Interviewer notes, as written" text={s.notes.untrusted_text} />
                </Card>
              ))}
            </Stack>
          )}
        </section>
      )}

      {evidence.emails && (
        <section aria-label="Emails">
          <h3>Emails</h3>
          {evidence.emails.length === 0 ? (
            <p className="muted">No emails yet.</p>
          ) : (
            <Stack gap={12}>
              {evidence.emails.map((m) => (
                <Card key={m.email_id}>
                  <p>
                    <strong>{m.direction === "inbound" ? "From the candidate" : `From ${m.sender}`}</strong>{" "}
                    <span className="mono muted">{m.email_id}</span>
                    <br />
                    <span className="muted">{formatDateTime(m.sent_at)}</span>
                  </p>
                  <FreeText
                    label={m.direction === "inbound" ? "Candidate-provided" : "Staff email"}
                    text={`${m.subject.untrusted_text}\n\n${m.body.untrusted_text}`}
                  />
                </Card>
              ))}
            </Stack>
          )}
        </section>
      )}

      {evidence.missing.length > 0 && (
        <p className="muted">Missing from the record: {evidence.missing.join("; ")}</p>
      )}
    </Stack>
  );
}

/** Load and show the evidence for one application, with loading, error, and not-found states. */
export function EvidenceView({ applicationId }: { applicationId: string }) {
  const result = useLoad(() => getCandidate(applicationId), applicationId);
  if (result.state === "loading")
    return (
      <div role="status">
        <span className="visually-hidden">Loading evidence</span>
        <Stack gap={10}>
          <Skeleton width="60%" />
          <Skeleton height={80} />
          <Skeleton height={80} />
        </Stack>
      </div>
    );
  if (result.state === "not_found") return <p>{applicationId} is not available. It may be outside the jobs your role can see.</p>;
  if (result.state === "error") return <ErrorState message={result.message} onRetry={result.reload} />;
  return <EvidenceBody evidence={result.data} />;
}
