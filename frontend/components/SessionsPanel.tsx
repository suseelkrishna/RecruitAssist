"use client";

/**
 * The saved chats beside the Ask conversation: newest first by default, with a switch to
 * show the oldest first, and eight chats a page. Each chat has its title, when it was last
 * updated, and a menu with Rename and Delete. The open chat is marked with aria-current.
 * Delete asks for confirmation first. For admin, when chats are kept in server memory, one
 * line says they reset when the server restarts. New chat lives in the Ask page header, so
 * it stays in reach when this panel is hidden.
 */

import { Button, DropdownMenu, Input, SegmentedControl } from "@suseelkrishna/fieryfusion-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";
import { PageControls, usePaged } from "@/components/Paged";
import { formatDateTime } from "@/lib/format";
import type { Conversation, Role } from "@/lib/types";

/** One chat in the list. Rename and Delete are in a "More actions" menu; each then shows a
 * small inline form in place of the item, so the choice can be confirmed or cancelled. */
function ChatItem({ chat, current, onOpen, onRename, onDelete }: {
  chat: Conversation;
  current: boolean;
  onOpen: () => void;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "delete">("view");
  const [title, setTitle] = useState(chat.title);
  const [failed, setFailed] = useState(false);
  const nameField = useRef<HTMLInputElement>(null);
  const cancelDelete = useRef<HTMLButtonElement>(null);

  // The menu returns focus to its button as it closes, so move focus into the form after that.
  useEffect(() => {
    if (mode === "view") return;
    const timer = window.setTimeout(() => (mode === "rename" ? nameField : cancelDelete).current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [mode]);

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await onRename(title);
      setMode("view");
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }

  if (mode === "rename")
    return (
      <li className="session-item">
        <form onSubmit={save} className="session-rename">
          <label className="visually-hidden" htmlFor={`rename-${chat.id}`}>
            New name for {chat.title}
          </label>
          <Input ref={nameField} id={`rename-${chat.id}`} value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setMode("view")} />
          <div className="session-actions">
            <Button type="submit" size="sm" disabled={!title.trim()}>
              Save
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setMode("view")}>
              Cancel
            </Button>
          </div>
          {failed && <p role="alert">The name could not be saved. Use 1 to 80 characters.</p>}
        </form>
      </li>
    );

  if (mode === "delete")
    return (
      <li className="session-item">
        <div className="session-rename" role="group" aria-label={`Delete ${chat.title}?`} onKeyDown={(e) => e.key === "Escape" && setMode("view")}>
          <p className="session-title">Delete &quot;{chat.title}&quot;?</p>
          <div className="session-actions">
            <Button size="sm" variant="danger" onClick={onDelete}>
              Delete
            </Button>
            <Button ref={cancelDelete} size="sm" variant="ghost" onClick={() => setMode("view")}>
              Cancel
            </Button>
          </div>
        </div>
      </li>
    );

  return (
    <li className="session-item session-row">
      <button type="button" className="session-open" aria-current={current ? "true" : undefined} onClick={onOpen}>
        <span className="session-title">{chat.title}</span>
        <span className="session-time">{formatDateTime(chat.updated_at)}</span>
      </button>
      <DropdownMenu
        trigger={
          <Button size="sm" variant="ghost" aria-label={`More actions for ${chat.title}`} className="session-more">
            ...
          </Button>
        }
        items={[
          { label: "Rename", onSelect: () => { setTitle(chat.title); setMode("rename"); } },
          { label: "Delete", onSelect: () => setMode("delete") },
        ]}
      />
    </li>
  );
}

/** Chats shown on one page of the panel. */
export const CHATS_PER_PAGE = 8;

const ORDERS = ["Newest", "Oldest"] as const;
type Order = (typeof ORDERS)[number];

/** The panel. `conversations` arrives newest first from the API; "Oldest" only reverses it. */
export function SessionsPanel({ conversations, currentId, role, storage, onOpen, onRename, onDelete }: {
  conversations: Conversation[];
  currentId: string | null;
  role: Role;
  storage?: "memory" | "redis";
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (id: string) => void;
}) {
  const [order, setOrder] = useState<Order>("Newest");
  const sorted = order === "Newest" ? conversations : [...conversations].reverse();
  const paged = usePaged(sorted, CHATS_PER_PAGE, order);

  return (
    <nav className="sessions" aria-label="Saved chats">
      <HeadingWithInfo
        as="h2"
        className="sessions-title"
        title="Saved chats"
        info="Your chats are saved for 30 days after their last question. The newest 50 are kept, with up to 30 questions each."
      />
      {conversations.length > 1 && (
        <SegmentedControl label="Sort chats" options={[...ORDERS]} value={order} onChange={(v) => setOrder(v as Order)} />
      )}
      {role === "admin" && storage === "memory" && (
        <p className="muted session-note">Saved chats are kept in server memory and reset when the server restarts.</p>
      )}
      {conversations.length === 0 ? (
        <p className="muted session-note">No saved chats yet. Your first question starts one.</p>
      ) : (
        <ul className="list-plain session-list">
          {paged.rows.map((chat) => (
            <ChatItem
              key={chat.id}
              chat={chat}
              current={chat.id === currentId}
              onOpen={() => onOpen(chat.id)}
              onRename={(title) => onRename(chat.id, title)}
              onDelete={() => onDelete(chat.id)}
            />
          ))}
        </ul>
      )}
      <PageControls paged={paged} noun="chats" label="Saved chats, pages" />
    </nav>
  );
}
