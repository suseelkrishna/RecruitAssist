/** The reassign dialog sends nothing until Confirm, then one POST with the picked recruiter and reason. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReassignDialog } from "@/components/ReassignDialog";
import type { JobDetail } from "@/lib/types";
import { setDemoUser } from "@/lib/user";
import { fakeFetch } from "./helpers";

const JOB = {
  job_id: "JOB-2",
  title: "Manufacturing Process Engineer",
  recruiter_user_id: "USR-4",
  recruiter_name: "Sam Rivera",
  can_reassign: true,
  reassign_options: [
    { user_id: "USR-5", name: "Alex Chen" },
    { user_id: "USR-6", name: "Jordan Patel" },
  ],
} as JobDetail;

/** Open the dialog, pick Alex Chen with a reason, and reach the confirmation step. */
async function reachConfirmation() {
  await userEvent.click(screen.getByRole("button", { name: "Reassign" }));
  await userEvent.selectOptions(screen.getByLabelText("New recruiter"), "USR-5");
  await userEvent.type(screen.getByLabelText("Reason (optional)"), "Balancing load");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  return screen.findByRole("alertdialog");
}

describe("ReassignDialog", () => {
  it("asks for confirmation with the exact wording and sends nothing before Confirm", async () => {
    const calls = fakeFetch(200, JOB);
    render(<ReassignDialog job={JOB} onDone={vi.fn()} />);
    const confirm = await reachConfirmation();
    expect(confirm.textContent).toContain("Reassign JOB-2 from Sam Rivera to Alex Chen?");
    expect(confirm.textContent).toContain("This is recorded in the change log.");
    expect(calls).toHaveLength(0);
  });

  it("sends nothing when the confirmation is cancelled", async () => {
    const calls = fakeFetch(200, JOB);
    render(<ReassignDialog job={JOB} onDone={vi.fn()} />);
    await reachConfirmation();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(calls).toHaveLength(0);
  });

  it("on Confirm sends one POST with the recruiter and reason, then reports success", async () => {
    setDemoUser("USR-2");
    const calls = fakeFetch(200, { ...JOB, recruiter_user_id: "USR-5", recruiter_name: "Alex Chen" });
    const onDone = vi.fn();
    render(<ReassignDialog job={JOB} onDone={onDone} />);
    await reachConfirmation();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/jobs/JOB-2/assignment");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ recruiter_user_id: "USR-5", reason: "Balancing load" });
    expect(onDone.mock.calls[0][1]).toContain("now assigned to Alex Chen");
  });

  it("shows the role message on 403", async () => {
    fakeFetch(403, { error: "Your role cannot reassign JOB-2." });
    render(<ReassignDialog job={JOB} onDone={vi.fn()} />);
    await reachConfirmation();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("You can't reassign this job.")).toBeTruthy();
  });
});
