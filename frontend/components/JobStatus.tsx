/** A job's status and target state, each shown with an icon and words, never color alone. */

import { StatusPill } from "@suseelkrishna/fieryfusion-react";

/** Open, or closed with the reason (filled or cancelled). */
export function JobStatus({ status }: { status: string }) {
  if (status === "open") return <StatusPill tone="info">Open</StatusPill>;
  if (status === "filled") return <StatusPill tone="success">Closed: filled</StatusPill>;
  return <StatusPill tone="warning">Closed: {status}</StatusPill>;
}

/** "Over target" for an open job past its target days, otherwise "On track" or nothing. */
export function TargetStatus({ overTarget, open }: { overTarget: boolean; open: boolean }) {
  if (!open) return <span className="muted">Closed</span>;
  return overTarget ? <StatusPill tone="warning">Over target</StatusPill> : <StatusPill tone="success">On track</StatusPill>;
}

/** A task's status: overdue or pending. */
export function TaskStatus({ status }: { status: string }) {
  return status === "overdue" ? <StatusPill tone="danger">Overdue</StatusPill> : <StatusPill tone="info">Pending</StatusPill>;
}
