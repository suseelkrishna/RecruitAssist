"use client";

/**
 * A record ID cited in an answer. An application ID such as APP-014 opens the evidence
 * drawer, a job ID links to the job page, and other IDs (emails, scorecards, tasks, stage
 * events) are shown as labels.
 */

import { Drawer } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { EvidenceView } from "@/components/EvidenceView";

export function CitationChip({ id }: { id: string }) {
  if (id.startsWith("APP-")) {
    return (
      <Drawer
        title={`Evidence for ${id}`}
        description="Stage timeline, CV excerpt, scorecards, and emails. Contact details are masked."
        trigger={
          <button type="button" className="chip" aria-label={`Open evidence for ${id}`}>
            {id}
          </button>
        }
      >
        <EvidenceView applicationId={id} />
      </Drawer>
    );
  }
  if (id.startsWith("JOB-")) {
    return (
      <Link className="chip" href={`/jobs/${id}`}>
        {id}
      </Link>
    );
  }
  return <span className="chip">{id}</span>;
}
