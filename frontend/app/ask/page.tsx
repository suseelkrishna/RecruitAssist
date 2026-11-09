"use client";

/**
 * Ask: a conversation with the assistant. The recruiter types a question, or picks a
 * suggested one for their role, and each reply comes back whole, already checked by the
 * verifier. Follow-up questions carry the last few answered turns as history. The scope
 * header comes from GET /api/me. A question can arrive prefilled from the dashboard through
 * ?q= and ?job=. Chats are saved per user and listed beside the conversation (in a drawer on
 * narrow screens); ?c= opens one. The conversation state lives in useChat.
 */

import { Button, Drawer, Field, Select, Stack } from "@suseelkrishna/fieryfusion-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ChatInput } from "@/components/ChatInput";
import { ChatThread } from "@/components/ChatThread";
import { ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { SessionsPanel } from "@/components/SessionsPanel";
import { getMe } from "@/lib/api";
import type { MeResponse, Role } from "@/lib/types";
import { useChat } from "@/lib/useChat";
import { useLoad } from "@/lib/useLoad";

type Suggestion = { question: string; about: string };

const SUGGESTIONS: Record<Role, Suggestion[]> = {
  hr_user: [
    { question: "What should I do today?", about: "Your overdue and pending tasks, most urgent first." },
    { question: "Top 3 candidates for my role", about: "The strongest active candidates, with the score behind each." },
    { question: "Who is waiting on me?", about: "Candidates and interviewers waiting on a reply or a decision." },
  ],
  hr_manager: [
    { question: "Where is my team losing candidates?", about: "The stages where candidates drop out, and why." },
    { question: "Which recruiter is overloaded?", about: "Active candidates and overdue tasks for each recruiter." },
    { question: "Which roles are behind target?", about: "Open jobs that have been open longer than planned." },
  ],
  admin: [
    { question: "Company-wide pipeline health", about: "Open jobs, candidates, offers, and overdue work across all teams." },
    { question: "Which sources bring the best candidates?", about: "How often applicants from each source reach Onsite and get hired." },
    { question: "Any integration issues?", about: "Sync status and recent errors for each connected system." },
  ],
};

/** The chat for the loaded user: saved chats beside the conversation and the question box. */
function Chat({ me, initialId, initialQuestion, initialJob }: { me: MeResponse; initialId: string | null; initialQuestion: string; initialJob: string }) {
  const { summary, scope, user } = me;
  const chat = useChat(user.user_id, initialId);
  const [question, setQuestion] = useState(initialQuestion);
  const [jobId, setJobId] = useState(initialJob);
  // Changes on every pick or New chat, so the drawer (keyed by it) closes even when the open chat stays the same.
  const [picks, setPicks] = useState(0);

  /** Send a question and clear the box. */
  function send(text: string) {
    setQuestion("");
    void chat.ask(text, jobId);
  }

  const panel = (
    <SessionsPanel
      conversations={chat.conversations}
      currentId={chat.conversationId}
      role={user.role}
      storage={chat.storage}
      onNew={() => {
        chat.newChat();
        setPicks((n) => n + 1);
      }}
      onOpen={(id) => {
        chat.openChat(id);
        setPicks((n) => n + 1);
      }}
      onRename={chat.rename}
      onDelete={(id) => void chat.remove(id)}
    />
  );

  return (
    <div className="ask-layout">
      <aside className="ask-sessions">{panel}</aside>
      <Stack gap={20} className="chat-page">
        <div className="page-head">
          <div>
            <h1>Ask</h1>
            <p>
              Your scope: {summary.jobs} jobs, {summary.active_candidates} candidates, {summary.overdue_tasks} overdue tasks
            </p>
          </div>
          <div className="ask-head-actions">
            <div className="ask-chats-button">
              {/* Keyed by the pick count, so picking or starting a chat closes the drawer. */}
              <Drawer
                key={picks}
                title="Chats"
                description="Your saved chats, newest first."
                trigger={<Button variant="secondary">Chats</Button>}
              >
                {panel}
              </Drawer>
            </div>
            <div className="field-narrow">
              <Field label="Limit to one job">
                <Select
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                  options={[{ label: "All jobs in my scope", value: "" }, ...scope.jobs.map((j) => ({ label: `${j.job_id} ${j.title}`, value: j.job_id }))]}
                />
              </Field>
            </div>
          </div>
        </div>

        {chat.turns.length === 0 ? (
          <section aria-labelledby="suggested">
            <h2 id="suggested" className="label-small">
              Try one of these
            </h2>
            <ul className="grid grid-3 list-plain" style={{ marginTop: 8 }}>
              {SUGGESTIONS[user.role].map((s) => (
                <li key={s.question}>
                  <button type="button" className="suggestion" onClick={() => send(s.question)}>
                    <span className="suggestion-question">{s.question}</span>
                    <span className="suggestion-about">{s.about}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <ChatThread turns={chat.turns} role={user.role} isOpen={chat.isOpen} onToggle={chat.toggle} onRetry={chat.retry} />
        )}

        <ChatInput value={question} onChange={setQuestion} onSend={send} onStop={chat.stop} waiting={chat.waiting} />
      </Stack>
    </div>
  );
}

function Ask() {
  const params = useSearchParams();
  const me = useLoad(getMe, "me");
  if (me.state === "loading") return <LoadingSkeleton blocks={2} label="Loading your scope" />;
  if (me.state === "error" || me.state === "not_found")
    return <ErrorState message={me.state === "error" ? me.message : "Your scope could not be loaded."} onRetry={me.reload} />;
  return <Chat me={me.data} initialId={params.get("c")} initialQuestion={params.get("q") ?? ""} initialJob={params.get("job") ?? ""} />;
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
