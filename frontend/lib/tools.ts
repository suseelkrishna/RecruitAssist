/**
 * Plain names for the assistant's tools, so pages can say what data an answer looked up
 * without showing internal function names. An unknown tool falls back to its own name.
 */

const TOOL_NAMES: Record<string, string> = {
  list_jobs: "Job list",
  pipeline_by_job: "Pipeline by job",
  funnel_dropoff: "Where candidates drop out",
  score_candidates: "Candidate ranking",
  get_candidate_evidence: "Candidate records",
  pending_tasks: "Tasks",
  source_quality: "Source quality",
  recruiter_load: "Recruiter workload",
  integration_health: "Integration status",
};

/** The plain name of one tool. */
export function toolName(tool: string): string {
  return TOOL_NAMES[tool] ?? tool;
}
