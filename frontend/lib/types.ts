/**
 * The shapes of the backend's JSON responses. They mirror what backend/app/main.py returns,
 * so pages can render fields without guessing. Pages never compute numbers from these.
 */

export type Role = "admin" | "hr_manager" | "hr_user";

export type DemoUser = { user_id: string; name: string; role: Role };

export type UsersResponse = { users: DemoUser[] };

export type ScopeJob = {
  job_id: string;
  title: string;
  status: string;
  days_open: number;
  active_by_stage: Record<string, number>;
  active_candidates: [string, string][];
};

export type MeResponse = {
  user: DemoUser;
  allowed_job_ids: string[];
  team_ids: string[];
  summary: { jobs: number; active_candidates: number; overdue_tasks: number };
  scope: { as_of: string; role: Role; jobs: ScopeJob[]; overdue_items: number };
};

export type Takeaway = { metric: string; as_of: string; takeaway: string };

export type FunnelStage = {
  stage: string;
  reached: number;
  in_stage: number;
  rejected: number;
  withdrawn: number;
  offer_declined: number;
  conversion_pct: number | null;
};

export type StageCandidate = { application_id: string; full_name: string; job_id: string };

export type Kpis = Takeaway & {
  open_jobs: number;
  active_candidates: number;
  new_applicants_7d: number;
  offers_out: number;
  median_days_to_fill: number | null;
  filled_jobs: number;
  overdue_tasks: number;
};

export type DaysOpenRow = {
  job_id: string;
  title: string;
  days_open: number;
  target_days: number;
  days_over_target: number;
  over_target: boolean;
};

export type WeekRow = { week_start: string; source?: string; applicants: number };

export type SourceRow = {
  source: string;
  applicants: number;
  reached_onsite: number;
  onsite_rate_pct: number | null;
  hires: number;
  median_days_to_hire: number | null;
  evidence: string[];
};

export type StageTime = { stage: string; median_days: number | null; stays: number };

export type WithdrawalReason = { reason: string; count: number; evidence: string[] };

export type RecruiterLoad = {
  recruiter_user_id: string;
  name: string;
  open_jobs: number;
  active_candidates: number;
  overdue_tasks: number;
  job_ids: string[];
};

export type DashboardOptions = {
  teams: { team_id: string; name: string }[];
  jobs: { job_id: string; title: string }[];
  recruiters: { user_id: string; name: string }[];
  range_days: number[];
};

export type DashboardResponse = {
  filters: Record<string, string | number>;
  options: DashboardOptions;
  kpis: Kpis;
  funnel: Takeaway & { stages: FunnelStage[] };
  stage_candidates: Record<string, StageCandidate[]>;
  days_open_vs_target: Takeaway & { jobs: DaysOpenRow[] };
  applicants_over_time: Takeaway & { by_source: boolean; weeks: WeekRow[] };
  applicants_total: Takeaway & { by_source: boolean; weeks: WeekRow[] };
  source_quality: Takeaway & { sources: SourceRow[] };
  time_in_stage: Takeaway & { stages: StageTime[] };
  withdrawal_reasons: Takeaway & { reasons: WithdrawalReason[] };
  offer_acceptance: Takeaway & {
    offers: number;
    accepted: string[];
    declined: string[];
    withdrawn: string[];
    pending: string[];
    acceptance_rate_pct: number | null;
  };
  recruiter_load: (Takeaway & { recruiters: RecruiterLoad[] }) | null;
};

export type DashboardFilters = { team?: string; job?: string; recruiter?: string; days?: string };

export type JobRow = {
  job_id: string;
  req_code: string;
  title: string;
  team_id: string;
  team: string;
  location: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  target_fill_days: number;
  active_applications: number;
  days_open: number;
  recruiter_user_id: string | null;
  recruiter_name: string | null;
};

export type BoardJob = JobRow & {
  hiring_manager: string;
  active_by_stage: { stage: string; count: number }[];
  overdue_tasks: number;
  over_target: boolean;
};

export type JobsResponse = {
  as_of: string;
  count: number;
  jobs: BoardJob[];
  teams: { team_id: string; name: string }[];
  recruiters: { user_id: string; name: string }[];
};

export type Task = {
  task_id?: string;
  rule_id?: string;
  matched_rule_id?: string;
  type?: string;
  title: string;
  job_id: string;
  application_id: string | null;
  owner_user_id: string | null;
  owner_name: string | null;
  due_at: string;
  status: "overdue" | "pending";
  days_overdue: number;
  evidence: string[];
};

export type ScoreComponent = { value: number; weighted: number; evidence: string[] };

export type RankedCandidate = {
  rank: number;
  application_id: string;
  candidate_id: string;
  full_name: string;
  current_stage: string;
  score: number;
  components: {
    scorecards: ScoreComponent & { count: number; avg_points: number | null };
    must_have: ScoreComponent & { avg_rating_by_skill: Record<string, number | null> };
    stage: ScoreComponent & { furthest_stage: string };
  };
  incomplete_evidence: boolean;
  missing: string[];
};

export type JobDetail = JobRow & {
  hiring_manager: string;
  over_target: boolean;
  must_haves: string[];
  nice_to_haves: string[];
  can_reassign: boolean;
  reassign_options: { user_id: string; name: string }[];
  funnel: FunnelStage[];
  candidates: Pick<RankedCandidate, "rank" | "application_id" | "full_name" | "current_stage" | "score" | "incomplete_evidence">[];
  candidate_pool: number;
  top_3: RankedCandidate[];
  rubric_weights: Record<string, number>;
  tasks: Task[];
};

export type Untrusted = { untrusted_text: string };

export type Evidence = {
  application_id: string;
  candidate_id: string;
  job_id: string;
  full_name: string;
  current_title: string;
  location: string;
  source: string;
  years_experience: number;
  current_stage: string;
  status: string;
  contact: { email: string; phone: string };
  as_of: string;
  missing: string[];
  cv?: Untrusted;
  scorecards?: {
    scorecard_id: string;
    interview_id: string;
    stage: string;
    interviewer: string;
    submitted_at: string;
    overall: string;
    ratings: Record<string, number>;
    notes: Untrusted;
  }[];
  emails?: {
    email_id: string;
    direction: "inbound" | "outbound";
    sent_at: string;
    sender: string;
    subject: Untrusted;
    body: Untrusted;
  }[];
  history?: {
    applied_at: string;
    stage_events: { event_id: string; stage: string; entered_at: string; exited_at: string | null; exit_type: string | null }[];
    interviews: { interview_id: string; stage: string; interviewer: string; scheduled_at: string; completed_at: string | null }[];
    outcome: { status: string; reason: string; at: string } | null;
  };
};

export type AskStep = { tool: string; input?: Record<string, unknown>; rows?: number; is_error?: boolean; ms?: number };

export type AskResult = {
  answer: string;
  status: string;
  verified: boolean;
  label: string;
  citations: string[];
  steps: AskStep[];
  usage?: {
    api_calls: number;
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens: number;
    cache_read_input_tokens: number;
    cache_hits: number;
  };
  latency_ms?: number;
  estimated_cost_usd?: number;
  model?: string;
  served_by?: string;
  verifier?: { passed: boolean; failures: string[]; checks: Record<string, { passed: boolean }> };
  as_of: string;
  job_id: string | null;
  source: "live" | "recording";
  recording_reason?: "live_limit" | "live_unavailable";
  recorded_at?: string;
};

export type AskBody = { question: string; job_id?: string };

export type BoardTask = Task & { team_id: string; team: string; kind: "explicit" | "derived"; rule_text: string | null };

export type TasksResponse = {
  as_of: string;
  count: number;
  overdue_count: number;
  tasks: BoardTask[];
  rules: Record<string, string>;
  group_by: "team" | "owner" | "none";
  groups: { key: string; label: string; count: number; overdue_count: number; tasks: BoardTask[] }[];
};

export type Integration = {
  integration: string;
  status: "Healthy" | "Degraded" | "Down";
  last_sync: string | null;
  mode: string;
  simulated: boolean;
  reasons?: string[];
  records?: number;
  runs_24h?: number;
  error_rate_24h_pct?: number | null;
  last_error?: { sync_id: string; at: string; message: Untrusted } | null;
};

export type SourcesResponse = {
  integrations_view: "full" | "summary";
  integrations: Integration[];
  source_quality: Takeaway & { sources: SourceRow[] };
};

export type LiveCheck = { name: string; status: "ok" | "error" | "not_configured"; [key: string]: unknown };

export type HealthResponse = { status: string; checks: LiveCheck[] };

export type ChangeEntry = {
  change_id: string;
  at: string;
  type: "reassignment" | "ask";
  user_id: string;
  user_name: string | null;
  user_role: Role | null;
  job_id: string | null;
  summary: string;
  reason?: string | null;
  question_hash?: string;
  tools?: string[];
  record_ids?: string[];
  source?: string;
  verified?: boolean;
};

export type ChangesResponse = { changes: ChangeEntry[] };

export type QualityResponse = {
  tests_defined: number;
  tests: unknown;
  mutation_score: unknown;
  rbac: unknown;
  scoreboard: unknown;
  generated_at: string | null;
  missing: string[];
};
