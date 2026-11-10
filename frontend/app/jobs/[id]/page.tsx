"use client";

/**
 * One job from GET /api/jobs/{id}: its funnel, ranked candidates, the top 3 with the score
 * breakdown, open tasks, and the current recruiter. Users the API marks with can_reassign see
 * a Reassign button. A job outside the user's scope comes back as 404 and shows not found.
 * The candidate table shows ten rows at a time and the task table five.
 */

import { ButtonLink, Card, DataTable, Stack, StatusPill, Toast } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "@/components/AppShell";
import { AXIS, COLORS, STILL, TOOLTIP } from "@/components/charts/theme";
import { CitationChip } from "@/components/CitationChip";
import { JobStatus, TargetStatus, TaskStatus } from "@/components/JobStatus";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { PageControls, usePaged } from "@/components/Paged";
import { ReassignForm } from "@/components/ReassignForm";
import { getJob } from "@/lib/api";
import { formatDate, show } from "@/lib/format";
import type { JobDetail, RankedCandidate, ScoreComponent } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

/** One row of the score breakdown: the component and the points it earned out of its maximum. */
function Component({ label, part, detail }: { label: string; part: ScoreComponent; detail: string }) {
  return (
    <div>
      <div className="stage-list" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>{label}</span>
        <span>
          {part.points} of {part.max_points} points
        </span>
      </div>
      <div className="score-bar" aria-hidden="true">
        <span style={{ width: `${part.value * 100}%` }} />
      </div>
      <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.875rem" }}>
        {detail}
      </p>
    </div>
  );
}

/** How the score out of 100 is made up, with the point limits the API reports. */
function rubricText(job: JobDetail): string {
  const parts = job.top_3[0]?.components;
  const limits = parts
    ? `up to ${parts.scorecards.max_points} points for scorecards, ${parts.must_have.max_points} for must-have skills, and ${parts.stage.max_points} for the stage reached`
    : "points for scorecards, must-have skills, and the stage reached";
  return `Each candidate is scored out of 100: ${limits}. Must-have skills are rated by interviewers, not taken from the CV.`;
}

/** The top 3 candidates, each with scorecards, must-have match, and stage reached. */
function TopThree({ job }: { job: JobDetail }) {
  return (
    <Card>
      <HeadingWithInfo as="h3" title="Top 3" info={rubricText(job)} />
      {job.top_3.length === 0 ? (
        <p className="muted">No active candidates to rank.</p>
      ) : (
        <ol className="list-plain" style={{ gap: 20 }}>
          {job.top_3.map((c: RankedCandidate) => (
            <li key={c.application_id}>
              <Stack gap={8}>
                <div className="card-actions">
                  <strong>
                    {c.rank}. {c.full_name}
                  </strong>
                  <CitationChip id={c.application_id} />
                  <span className="muted">{c.current_stage}</span>
                  <span>
                    <strong>{c.score_100}</strong> out of 100
                  </span>
                  {c.incomplete_evidence && <StatusPill tone="warning">Scorecards missing</StatusPill>}
                </div>
                <Component
                  label="Scorecards"
                  part={c.components.scorecards}
                  detail={`${c.components.scorecards.count} scorecards, average ${show(c.components.scorecards.avg_points)} of 4.`}
                />
                <Component
                  label="Must-have match"
                  part={c.components.must_have}
                  detail={Object.entries(c.components.must_have.avg_rating_by_skill)
                    .map(([skill, rating]) => `${skill}: ${rating === null ? "not rated" : `${rating} of 4`}`)
                    .join("; ")}
                />
                <Component
                  label="Stage reached"
                  part={c.components.stage}
                  detail={`Furthest stage: ${c.components.stage.furthest_stage}.`}
                />
                {c.missing.length > 0 && <p className="muted">Missing: {c.missing.join("; ")}</p>}
              </Stack>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function JobPage({ job, onReassigned }: { job: JobDetail; onReassigned: (message: string) => void }) {
  const askHref = `/ask?job=${job.job_id}&q=${encodeURIComponent(`How is the ${job.title} role going, and what needs attention?`)}`;

  return (
    <Stack gap={20} className="fade-in">
      <div className="page-head">
        <div>
          <p className="label-small">
            <Link href="/jobs" className="ff-link">
              Jobs
            </Link>{" "}
            / {job.job_id} / <span className="mono">{job.req_code}</span>
          </p>
          <h1>{job.title}</h1>
          <p>
            {job.team}, {job.location}. Hiring manager: {job.hiring_manager}. Opened {formatDate(job.opened_at)}.
          </p>
        </div>
        <ButtonLink as={Link} href={askHref} variant="primary">
          Ask about this job
        </ButtonLink>
      </div>

      <div className="grid grid-2">
        <Card title="Status">
          <div className="card-actions">
            <JobStatus status={job.status} />
            <TargetStatus overTarget={job.over_target} open={job.status === "open"} />
          </div>
          <dl className="kv" style={{ marginTop: 12 }}>
            <dt>Days open</dt>
            <dd>{job.days_open}</dd>
            <dt>Target days</dt>
            <dd>{job.target_fill_days}</dd>
            <dt>Active candidates</dt>
            <dd>{job.active_applications}</dd>
            <dt>Must-haves</dt>
            <dd>{job.must_haves.join(", ")}</dd>
          </dl>
        </Card>
        <Card title="Recruiter">
          <p style={{ fontSize: "1.125rem", margin: "0 0 12px" }}>{job.recruiter_name ?? "Unassigned"}</p>
          {job.can_reassign ? (
            <ReassignForm
              key={job.recruiter_user_id ?? "none"}
              job={job}
              onDone={(_, message) => onReassigned(message)}
            />
          ) : (
            <p className="muted">Your role cannot reassign this job.</p>
          )}
        </Card>
      </div>

      <Card>
        <HeadingWithInfo as="h3" title="Funnel" info="Applications that reached each stage, with rejections and withdrawals." />
        {job.funnel[0]?.reached ? (
          <div className="chart-box" role="img" aria-label={job.funnel.map((s) => `${s.stage}: ${s.reached} reached`).join(", ")}>
            <ResponsiveContainer>
              <BarChart data={job.funnel} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="stage" {...AXIS} interval={0} fontSize={11} angle={-25} textAnchor="end" height={56} />
                <YAxis {...AXIS} allowDecimals={false} />
                <Tooltip {...TOOLTIP} />
                <Legend />
                <Bar dataKey="reached" name="Reached" fill={COLORS.main} {...STILL} />
                <Bar dataKey="rejected" name="Rejected" fill={COLORS.second} {...STILL} />
                <Bar dataKey="withdrawn" name="Withdrawn" fill={COLORS.third} {...STILL} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted">No applications yet.</p>
        )}
      </Card>

      <TopThree job={job} />

      <Card>
        <HeadingWithInfo as="h3" title="Candidates" info="Active candidates, ranked by the same score as the Top 3." />
        {job.candidates.length === 0 ? (
          <Empty title="No active candidates" description="This job has no active applications." />
        ) : (
          <PagedTable
            items={job.candidates}
            size={10}
            noun="candidates"
            caption="Active candidates, ranked"
            columns={["Rank", "Candidate", "Application", "Stage", "Score", "Scorecards"]}
            row={(c) => [
              c.rank,
              c.full_name,
              <CitationChip key="id" id={c.application_id} />,
              c.current_stage,
              <span key="score">{c.score_100} / 100</span>,
              c.incomplete_evidence ? <StatusPill key="ev" tone="warning">Scorecards missing</StatusPill> : <StatusPill key="ev" tone="success">Scorecards in</StatusPill>,
            ]}
          />
        )}
      </Card>

      <Card>
        <HeadingWithInfo as="h3" title="Tasks" info="Open tasks on this job, most overdue first." />
        {job.tasks.length === 0 ? (
          <Empty title="No open tasks" description="Nothing is pending or overdue on this job." />
        ) : (
          <PagedTable
            items={job.tasks}
            size={5}
            noun="tasks"
            caption="Open tasks on this job"
            columns={["Status", "Task", "Owner", "Due", "Days overdue", "Kind", "Evidence"]}
            row={(t) => [
              <TaskStatus key="s" status={t.status} />,
              t.title,
              t.owner_name ?? "Unassigned",
              formatDate(t.due_at),
              t.status === "overdue" ? t.days_overdue : "",
              t.task_id ? `Explicit (${t.task_id})` : `Derived (${t.rule_id})`,
              <span className="chips" key="e">
                {t.evidence.map((id) => (
                  <CitationChip key={id} id={id} />
                ))}
              </span>,
            ]}
          />
        )}
      </Card>
    </Stack>
  );
}

/** A kit table that shows `size` rows at a time, with page buttons when there are more. */
function PagedTable<T>({ items, size, noun, caption, columns, row }: {
  items: T[];
  size: number;
  noun: string;
  caption: string;
  columns: string[];
  row: (item: T) => ReactNode[];
}) {
  const paged = usePaged(items, size);
  return (
    <>
      <DataTable caption={caption} columns={columns} rows={paged.rows.map(row)} />
      <PageControls paged={paged} noun={noun} label={`${caption}, pages`} />
    </>
  );
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const result = useLoad(() => getJob(id), id);
  const [toast, setToast] = useState<string | null>(null);
  if (result.state === "not_found") notFound();
  return (
    <AppShell>
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
      {result.state === "loading" && <LoadingSkeleton blocks={4} label="Loading the job" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {result.state === "ready" && <JobPage
          job={result.data}
          onReassigned={(message) => {
            setToast(message);
            result.reload();
          }}
        />}
    </AppShell>
  );
}
