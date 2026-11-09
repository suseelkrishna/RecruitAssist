/** Citation chips: an APP- chip opens the evidence drawer with labeled, masked evidence. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CitationChip } from "@/components/CitationChip";
import type { Evidence } from "@/lib/types";
import { fakeFetch } from "./helpers";

const EVIDENCE: Evidence = {
  application_id: "APP-014",
  candidate_id: "CAN-014",
  job_id: "JOB-5",
  full_name: "Orrin Thistlewood",
  current_title: "Metrology Technician",
  location: "Madison, WI",
  source: "Job board",
  years_experience: 6,
  current_stage: "Applied",
  status: "rejected",
  contact: { email: "[email hidden]", phone: "[phone hidden]" },
  as_of: "2026-11-09T17:00:00Z",
  missing: [],
  cv: { untrusted_text: "Summary: Metrology Technician with 6 years in industry." },
  scorecards: [],
  emails: [
    {
      email_id: "EM-001",
      direction: "inbound",
      sent_at: "2026-03-18T10:00:00Z",
      sender: "candidate",
      subject: { untrusted_text: "Question" },
      body: { untrusted_text: "Is the role remote?" },
    },
  ],
  history: {
    applied_at: "2026-03-17T20:17:00Z",
    stage_events: [
      { event_id: "EV-0036", stage: "Applied", entered_at: "2026-03-17T20:17:00Z", exited_at: "2026-03-19T11:27:00Z", exit_type: "rejected" },
    ],
    interviews: [],
    outcome: { status: "rejected", reason: "Does not meet must-have requirements", at: "2026-03-19T11:27:00Z" },
  },
};

describe("CitationChip", () => {
  it("opens the evidence drawer for an application and loads it once", async () => {
    const calls = fakeFetch(200, EVIDENCE);
    render(<CitationChip id="APP-014" />);
    expect(calls).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Open evidence for APP-014" }));
    expect(await screen.findByRole("dialog", { name: "Evidence for APP-014" })).toBeTruthy();
    expect(await screen.findByText("EV-0036")).toBeTruthy();
    expect(calls.map((c) => c.url)).toEqual(["/api/candidates/APP-014"]);
  });

  it("labels candidate text and shows contact details masked", async () => {
    fakeFetch(200, EVIDENCE);
    render(<CitationChip id="APP-014" />);
    await userEvent.click(screen.getByRole("button", { name: "Open evidence for APP-014" }));
    await screen.findByText("EV-0036");
    expect(screen.getAllByText("Candidate-provided")).toHaveLength(2);
    expect(screen.getByText("[email hidden]")).toBeTruthy();
    expect(screen.getByText("[phone hidden]")).toBeTruthy();
  });

  it("links a job ID to the job page and shows other IDs as labels", () => {
    render(
      <>
        <CitationChip id="JOB-2" />
        <CitationChip id="SC-045" />
      </>,
    );
    expect(screen.getByRole("link", { name: "JOB-2" }).getAttribute("href")).toBe("/jobs/JOB-2");
    expect(screen.queryByRole("button", { name: /SC-045/ })).toBeNull();
    expect(screen.getByText("SC-045")).toBeTruthy();
  });
});
