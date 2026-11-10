"use client";

/**
 * Pending and overdue tasks from GET /api/tasks. The API groups them for the role: HR Users
 * see their own tasks, HR Managers their teams' tasks by recruiter, and Admin every task by
 * team. Each task is marked Explicit or Derived, and a derived task shows the rule behind it.
 * Each group shows five tasks at a time, with page buttons when there are more.
 */

import { Badge, Card, DataTable, Stack } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { CitationChip } from "@/components/CitationChip";
import { TaskStatus } from "@/components/JobStatus";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { PageControls, usePaged } from "@/components/Paged";
import { getTasks } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { BoardTask, TasksResponse } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

/** "Explicit" for a row in the tasks table, "Derived" for a task found in the records. */
function Kind({ task }: { task: BoardTask }) {
  return <Badge tone="neutral">{task.kind === "derived" ? "Derived" : "Explicit"}</Badge>;
}

/** The task title, with the rule that created it (or that it also matches) underneath. */
function Title({ task }: { task: BoardTask }) {
  return (
    <div style={{ minWidth: 260 }}>
      {task.title}
      {task.rule_text && (
        <div className="muted" style={{ fontSize: "0.875rem" }}>
          {task.kind === "derived" ? "Rule" : "Also matches the rule"}: {task.rule_text}
        </div>
      )}
    </div>
  );
}

/** "1 task" or "3 tasks". */
function tasksLabel(count: number, overdue: number): string {
  return `${count} ${count === 1 ? "task" : "tasks"}, ${overdue} overdue`;
}

/** Tasks shown on one page of a group. */
const TASKS_PER_PAGE = 5;

/** One group's tasks as a table, a page at a time. */
function TaskTable({ tasks, caption }: { tasks: BoardTask[]; caption: string }) {
  const paged = usePaged(tasks, TASKS_PER_PAGE);
  return (
    <>
    <DataTable
      caption={caption}
      columns={["Status", "Kind", "Task", "Job", "Owner", "Due", "Days overdue", "Evidence"]}
      rows={paged.rows.map((t) => [
        <TaskStatus key="status" status={t.status} />,
        <Kind key="kind" task={t} />,
        <Title key="title" task={t} />,
        <Link key="job" className="ff-link" href={`/jobs/${t.job_id}`}>
          {t.job_id}
        </Link>,
        t.owner_name ?? "Unassigned",
        formatDate(t.due_at),
        t.status === "overdue" ? t.days_overdue : "",
        <span className="chips" key="evidence">
          {t.evidence.map((id) => (
            <CitationChip key={id} id={id} />
          ))}
        </span>,
      ])}
    />
    <PageControls paged={paged} noun="tasks" label={`${caption}, pages`} />
    </>
  );
}

export default function TasksPage() {
  const result = useLoad(getTasks, "tasks");
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <HeadingWithInfo as="h1" title="Tasks" info="Overdue and pending work, most overdue first." />
        </div>
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={2} label="Loading tasks" />}
      {(result.state === "error" || result.state === "not_found") && (
        <ErrorState message={result.state === "error" ? result.message : "Tasks could not be loaded."} onRetry={result.reload} />
      )}
      {result.state === "ready" &&
        (result.data.count === 0 ? (
          <Empty title="Nothing pending" description="There are no pending or overdue tasks in your scope." />
        ) : (
          <Stack gap={16} className="fade-in">
            {result.data.groups.map((g) => (
              <Card key={g.key} title={g.label} description={tasksLabel(g.count, g.overdue_count)}>
                <TaskTable tasks={g.tasks} caption={`Tasks: ${g.label}`} />
              </Card>
            ))}
            <Card>
              <HeadingWithInfo as="h3" title="Rules for derived tasks" info="Derived tasks come from the records when one of these rules fires." />
              <dl className="kv">
                {Object.entries(result.data.rules).map(([id, text]) => (
                  <div key={id} style={{ display: "contents" }}>
                    <dt className="mono">{id}</dt>
                    <dd>{text}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </Stack>
        ))}
    </AppShell>
  );
}
