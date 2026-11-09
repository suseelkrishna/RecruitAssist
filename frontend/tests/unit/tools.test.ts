/** Tool names shown to people are plain words, and an unknown tool still shows something. */

import { describe, expect, it } from "vitest";
import { toolName } from "@/lib/tools";

describe("toolName", () => {
  it("gives every assistant tool a plain name", () => {
    const tools = ["list_jobs", "pipeline_by_job", "funnel_dropoff", "score_candidates", "get_candidate_evidence",
      "pending_tasks", "source_quality", "recruiter_load", "integration_health"];
    for (const tool of tools) {
      expect(toolName(tool)).not.toBe(tool);
      expect(toolName(tool)).not.toContain("_");
    }
  });

  it("falls back to the tool's own name", () => {
    expect(toolName("new_tool")).toBe("new_tool");
  });
});
