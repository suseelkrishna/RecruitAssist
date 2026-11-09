"use client";

/**
 * Ask: the recruiter types a question, or picks a suggested one for their role, and the page
 * sends it to POST /api/ask once. The answer comes back whole, already checked by the
 * verifier, with citations that open the evidence drawer. The scope header comes from
 * GET /api/me. A question can arrive prefilled from the dashboard through ?q= and ?job=.
 */

import { Alert, Button, Card, Field, Select, Stack, Textarea } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { AnswerText } from "@/components/AnswerText";
import { AppShell } from "@/components/AppShell";
import { BehindTheScenes } from "@/components/BehindTheScenes";
import { CitationChip } from "@/components/CitationChip";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { VerifierBadge } from "@/components/VerifierBadge";
import { ApiError, ask, getMe } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AskResult, Role } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

const CHIPS: Record<Role, string[]> = {
  hr_user: ["What should I do today?", "Top 3 candidates for my role", "Who is waiting on me?"],
  hr_manager: ["Where is my team losing candidates?", "Which recruiter is overloaded?", "Which roles are behind target?"],
  admin: ["Company-wide pipeline health", "Which sources bring the best candidates?", "Any integration issues?"],
};

/** The dashboard panel that shows the same numbers as a question, for when asking fails. */
function dashboardLinkFor(question: string): string {
  const q = question.toLowerCase();
  if (q.includes("losing") || q.includes("pipeline")) return "/dashboard#funnel";
  if (q.includes("overloaded") || q.includes("recruiter")) return "/dashboard#recruiter-load";
  if (q.includes("target") || q.includes("behind")) return "/dashboard#days-open";
  if (q.includes("source")) return "/dashboard#source-quality";
  if (q.includes("withdr")) return "/dashboard#withdrawals";
  if (q.includes("offer")) return "/dashboard#offers";
  return "/dashboard";
}

/** The note shown above a recorded answer. A recording is never shown without it. */
function recordingNote(result: AskResult): string {
  return result.recording_reason === "live_unavailable"
    ? "Showing a recorded answer because live answers are not available right now."
    : "Showing a recorded answer because the live limit was reached.";
}

type Turn = { question: string; result: AskResult };

/** One finished answer with its verifier badge, citations, and the behind the scenes panel. */
function AnswerCard({ turn }: { turn: Turn }) {
  const { result } = turn;
  return (
    <Card className="fade-in">
      <Stack gap={12}>
        <p className="label-small">You asked</p>
        <p style={{ margin: 0, fontWeight: 600 }}>{turn.question}</p>
        {result.source === "recording" && (
          <Alert tone="info" title="Recorded answer">
            {recordingNote(result)} Recorded {formatDateTime(result.recorded_at)}.
          </Alert>
        )}
        <VerifierBadge result={result} />
        <AnswerText text={result.answer} />
        {result.citations.length > 0 && (
          <div>
            <p className="label-small">Sources</p>
            <div className="chips">
              {result.citations.map((id) => (
                <CitationChip key={id} id={id} />
              ))}
            </div>
          </div>
        )}
        <BehindTheScenes result={result} />
      </Stack>
    </Card>
  );
}

/** "Checking the data..." with the seconds waited so far. */
function Waiting() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <Card>
      <p role="status" aria-live="polite" style={{ margin: 0 }}>
        Checking the data... {seconds}s
      </p>
    </Card>
  );
}

function Ask() {
  const params = useSearchParams();
  const me = useLoad(getMe, "me");
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [jobId, setJobId] = useState(params.get("job") ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [waiting, setWaiting] = useState(false);
  const [failure, setFailure] = useState<{ question: string; message: string } | null>(null);

  /** Send one question and add the answer to the page. */
  async function send(text: string) {
    const q = text.trim();
    if (!q || waiting) return;
    setWaiting(true);
    setFailure(null);
    try {
      const result = await ask({ question: q, ...(jobId ? { job_id: jobId } : {}) });
      setTurns((t) => [{ question: q, result }, ...t]);
      setQuestion("");
    } catch (error) {
      setFailure({ question: q, message: error instanceof ApiError ? error.message : "The assistant could not answer." });
    } finally {
      setWaiting(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(question);
  }

  if (me.state === "loading") return <LoadingSkeleton blocks={2} label="Loading your scope" />;
  if (me.state === "error" || me.state === "not_found")
    return <ErrorState message={me.state === "error" ? me.message : "Your scope could not be loaded."} onRetry={me.reload} />;
  const { summary, scope, user } = me.data;

  return (
    <Stack gap={20}>
      <div className="page-head">
        <div>
          <h1>Ask</h1>
          <p>
            Your scope: {summary.jobs} jobs, {summary.active_candidates} candidates, {summary.overdue_tasks} overdue tasks
          </p>
        </div>
        <Field label="Job focus">
          <Select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            options={[{ label: "All jobs in my scope", value: "" }, ...scope.jobs.map((j) => ({ label: `${j.job_id} ${j.title}`, value: j.job_id }))]}
          />
        </Field>
      </div>

      <div>
        <p className="label-small">Suggested questions</p>
        <div className="card-actions">
          {CHIPS[user.role].map((chip) => (
            <Button key={chip} variant="secondary" size="sm" disabled={waiting} onClick={() => void send(chip)}>
              {chip}
            </Button>
          ))}
        </div>
      </div>

      <form onSubmit={onSubmit}>
        <Stack gap={12}>
          <Field label="Your question" hint="Answers use only the jobs in your scope. The assistant cannot change any record.">
            <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} maxLength={1000} />
          </Field>
          <div>
            <Button type="submit" loading={waiting} disabled={!question.trim()}>
              Ask
            </Button>
          </div>
        </Stack>
      </form>

      {waiting && <Waiting />}

      {failure && (
        <Alert tone="warning" title="The assistant could not answer this one">
          {failure.message} You can still see the numbers on the{" "}
          <Link className="ff-link" href={dashboardLinkFor(failure.question)}>
            matching dashboard table
          </Link>
          .
        </Alert>
      )}

      {turns.length === 0 && !waiting && !failure && (
        <p className="muted">No questions yet. Pick a suggested question or type your own.</p>
      )}
      {turns.map((turn, i) => (
        <AnswerCard key={turns.length - i} turn={turn} />
      ))}
    </Stack>
  );
}

export default function AskPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingSkeleton blocks={2} label="Loading" />}>
        <Ask />
      </Suspense>
    </AppShell>
  );
}
