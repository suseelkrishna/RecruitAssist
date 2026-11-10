"use client";

/**
 * One turn of the Ask conversation: the question in a bubble on the right with the user's
 * initials beside it, and the assistant's reply on the left beside RecruitBot. The reply is a waiting counter while the answer is on its
 * way, the answer with its badges and hidden evidence when it arrives, or a note with Retry
 * when the question was stopped or failed.
 */

import { Avatar, Button } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AnswerText } from "@/components/AnswerText";
import { MessageBadges } from "@/components/MessageBadges";
import { MessageEvidence } from "@/components/MessageEvidence";
import { RecruitBot } from "@/components/RecruitBot";
import type { Role } from "@/lib/types";
import type { Panel, Turn } from "@/lib/useChat";

/** The dashboard panel that shows the same numbers as a question, for when asking fails. */
export function dashboardLinkFor(question: string): string {
  const q = question.toLowerCase();
  if (q.includes("losing") || q.includes("pipeline")) return "/dashboard#funnel";
  if (q.includes("overloaded") || q.includes("recruiter")) return "/dashboard#recruiter-load";
  if (q.includes("target") || q.includes("behind")) return "/dashboard#days-open";
  if (q.includes("source")) return "/dashboard#source-quality";
  if (q.includes("withdr")) return "/dashboard#withdrawals";
  if (q.includes("offer")) return "/dashboard#offers";
  return "/dashboard";
}

/** "Checking the data..." with the seconds waited so far. */
function Waiting() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <p role="status" style={{ margin: 0 }}>
      Checking the data... {seconds}s
    </p>
  );
}

export function ChatMessage({ turn, role, userName, isOpen, onToggle, onRetry }: {
  turn: Turn;
  role: Role;
  userName: string;
  isOpen: (panel: Panel) => boolean;
  onToggle: (panel: Panel) => void;
  onRetry: () => void;
}) {
  return (
    <li className="chat-turn">
      <div className="chat-row chat-row-user">
        <div className="bubble bubble-user">
          <span className="visually-hidden">You asked: </span>
          {turn.question}
        </div>
        <span className="chat-avatar" aria-hidden="true">
          <Avatar name={userName} size="sm" />
        </span>
      </div>
      <div className="chat-row chat-row-assistant">
      <span className="chat-avatar">
        <RecruitBot size={34} />
      </span>
      <div className="bubble bubble-assistant" aria-busy={turn.state === "pending"}>
        <span className="visually-hidden">Assistant: </span>
        {turn.state === "pending" && <Waiting />}
        {turn.state === "stopped" && (
          <div className="message-note">
            <p style={{ margin: 0 }}>Stopped.</p>
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}
        {turn.state === "error" && (
          <div className="message-note">
            <p style={{ margin: 0 }}>
              {turn.error} You can still see the numbers on the{" "}
              <Link className="ff-link" href={dashboardLinkFor(turn.question)}>
                matching dashboard table
              </Link>
              .
            </p>
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}
        {turn.state === "answered" && turn.result && (
          <>
            <MessageBadges result={turn.result} />
            <AnswerText text={turn.result.answer} />
            <MessageEvidence id={turn.id} result={turn.result} role={role} isOpen={isOpen} onToggle={onToggle} />
          </>
        )}
      </div>
      </div>
    </li>
  );
}
