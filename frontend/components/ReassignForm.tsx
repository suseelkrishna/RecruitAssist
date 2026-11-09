"use client";

/**
 * Reassign a job's recruiter, the only write in the app. The recruiter picker (from the job's
 * reassign_options) and an optional reason sit on the job page. "Reassign" opens a confirmation
 * that names the job, the current recruiter, and the new one, and nothing is sent until Confirm
 * is pressed. There is no undo: reassigning back is a new entry in the change log.
 */

import { Alert, Button, ConfirmDialog, Field, Select, Stack, Textarea } from "@suseelkrishna/fieryfusion-react";
import { useState } from "react";
import { ApiError, reassignJob } from "@/lib/api";
import type { JobDetail } from "@/lib/types";

export function ReassignForm({ job, onDone }: { job: JobDetail; onDone: (updated: JobDetail, message: string) => void }) {
  const [recruiter, setRecruiter] = useState(job.reassign_options[0]?.user_id ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const target = job.reassign_options.find((o) => o.user_id === recruiter);
  const from = job.recruiter_name ?? "no recruiter";

  /** Send the reassignment. Called only from the confirmation's Confirm button. */
  async function confirm() {
    if (!target) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await reassignJob(job.job_id, target.user_id, reason.trim() || undefined);
      onDone(updated, `${job.job_id} is now assigned to ${target.name}. The change is in the change log.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setError("You can't reassign this job.");
      else setError(e instanceof ApiError ? e.message : "The job could not be reassigned. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap={12}>
      <Field label="Reassign to">
        <Select value={recruiter} onChange={(e) => setRecruiter(e.target.value)} options={job.reassign_options.map((o) => ({ label: o.name, value: o.user_id }))} />
      </Field>
      <Field label="Reason (optional)">
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} rows={2} />
      </Field>
      {error && (
        <Alert tone="danger" title="Not reassigned">
          {error}
        </Alert>
      )}
      <div>
        <ConfirmDialog
          title={`Reassign ${job.job_id} from ${from} to ${target?.name ?? ""}?`}
          description="This is recorded in the change log."
          confirmLabel="Confirm"
          cancelLabel="Cancel"
          onConfirm={() => void confirm()}
          trigger={
            <Button variant="secondary" disabled={!target} loading={saving}>
              Reassign
            </Button>
          }
        />
      </div>
    </Stack>
  );
}
