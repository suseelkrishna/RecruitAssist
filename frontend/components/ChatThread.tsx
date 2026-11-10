"use client";

/**
 * The Ask conversation, oldest turn first. It is a live log, so screen readers announce new
 * replies, and it scrolls the newest turn into view whenever the conversation changes.
 */

import { useEffect, useRef } from "react";
import { ChatMessage } from "@/components/ChatMessage";
import type { Role } from "@/lib/types";
import type { Panel, Turn } from "@/lib/useChat";

export function ChatThread({ turns, role, userName, isOpen, onToggle, onRetry }: {
  turns: Turn[];
  role: Role;
  userName: string;
  isOpen: (id: string, panel: Panel) => boolean;
  onToggle: (id: string, panel: Panel) => void;
  onRetry: (id: string) => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const latest = turns.length > 0 ? `${turns[turns.length - 1].id}:${turns[turns.length - 1].state}` : "";
  useEffect(() => {
    if (latest) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [latest]);

  return (
    <div className="chat-thread" role="log" aria-live="polite" aria-label="Conversation">
      <ol className="list-plain chat-list">
        {turns.map((turn) => (
          <ChatMessage
            key={turn.id}
            turn={turn}
            role={role}
            userName={userName}
            isOpen={(panel) => isOpen(turn.id, panel)}
            onToggle={(panel) => onToggle(turn.id, panel)}
            onRetry={() => onRetry(turn.id)}
          />
        ))}
      </ol>
      <div ref={end} className="chat-end" />
    </div>
  );
}
