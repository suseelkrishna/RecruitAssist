"use client";

/**
 * The Ask conversation state in one place: the user's saved chats, the open chat and its
 * turns, which evidence and trace panels are open per turn, and the actions on them.
 *
 * Chats are saved on the backend. The first question in a new chat creates it, and every
 * question is asked with its conversation_id so the answer is saved as a turn. The open chat's
 * ID is kept in the URL as ?c=, so a reload or a new tab reopens it. A copy in localStorage
 * (lib/chatCache.ts) shows chats at once while the backend copy loads. When the window regains
 * focus, or another tab changes the cache, the list and the open chat are fetched again, so a
 * question asked in another tab appears here; a question still on its way in this tab is kept.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  ask,
  createConversation,
  deleteConversation,
  getConversation,
  isNotFound,
  listConversations,
  renameConversation,
} from "@/lib/api";
import { cacheChat, cachedChat, cachedList, cacheKey, cacheList, forgetChat } from "@/lib/chatCache";
import type { AskHistoryItem, AskResult, Conversation, ConversationDetail } from "@/lib/types";

/** How many earlier finished turns go with a follow-up question. */
export const HISTORY_TURNS = 6;

export type TurnState = "pending" | "answered" | "error" | "stopped";

export type Turn = {
  id: string;
  question: string;
  jobId: string;
  state: TurnState;
  result?: AskResult;
  error?: string;
};

export type Panel = "evidence" | "trace";

/** The last HISTORY_TURNS answered turns as {question, answer, citations}. Errored and stopped turns are left out. */
export function historyFrom(turns: Turn[]): AskHistoryItem[] {
  return turns
    .filter((t) => t.state === "answered" && t.result)
    .slice(-HISTORY_TURNS)
    .map((t) => ({ question: t.question, answer: t.result!.answer, citations: t.result!.citations }));
}

/** A saved chat's turns as answered turns. */
function turnsFrom(chat: ConversationDetail): Turn[] {
  return chat.turns.map((t) => ({ id: t.turn_id, question: t.question, jobId: t.job_id ?? "", state: "answered", result: t }));
}

/** The saved turns, followed by any turn of this tab that is not saved yet (on its way, stopped, or failed). */
function merge(saved: Turn[], local: Turn[]): Turn[] {
  const ids = new Set(saved.map((t) => t.id));
  return [...saved, ...local.filter((t) => t.state !== "answered" && !ids.has(t.id))];
}

/** True when the error came from aborting the request with the Stop button. */
function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Put the open chat's ID in the address bar as ?c=, or remove it, without a navigation. */
function putChatInUrl(id: string | null): void {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("c", id);
  else url.searchParams.delete("c");
  window.history.replaceState(window.history.state, "", url);
}

/**
 * The chat state for one demo user. The page mounts this only in the browser, after the user
 * has loaded, so the cached list and chat can be read straight away. Ask opens on a new, empty
 * chat; ?c= opens a saved one instead.
 */
export function useChat(userId: string, initialId: string | null) {
  const [startId] = useState(initialId);
  const [conversations, setConversations] = useState<Conversation[]>(() => cachedList(userId));
  const [storage, setStorage] = useState<"memory" | "redis" | undefined>(undefined);
  const [conversationId, setConversationId] = useState<string | null>(startId);
  const [turns, setTurns] = useState<Turn[]>(() => {
    const cached = startId ? cachedChat(userId, startId) : null;
    return cached ? turnsFrom(cached) : [];
  });
  const [open, setOpen] = useState<Record<string, Panel[]>>({});
  const controller = useRef<AbortController | null>(null);
  const counter = useRef(0);
  const current = useRef<string | null>(startId);
  const waiting = turns.some((t) => t.state === "pending");

  /** Fetch the chat list and cache it. */
  const refreshList = useCallback(
    (): Promise<Conversation[] | null> =>
      listConversations().then(
        (body) => {
          setConversations(body.conversations);
          setStorage(body.storage);
          cacheList(userId, body.conversations);
          return body.conversations;
        },
        () => null,
      ),
    [userId],
  );

  /** Fetch one chat and show it, keeping turns of this tab that are not saved yet. A chat that
   * is not this user's, or was deleted, gives way to an empty chat. */
  const loadChat = useCallback(
    (id: string) =>
      getConversation(id).then(
        (chat) => {
          cacheChat(userId, chat);
          if (current.current === id) setTurns((local) => merge(turnsFrom(chat), local));
        },
        (error: unknown) => {
          if (!isNotFound(error) || current.current !== id) return;
          current.current = null;
          setConversationId(null);
          setTurns([]);
          putChatInUrl(null);
        },
      ),
    [userId],
  );

  /** Show a chat: the cached copy first, then the backend copy. */
  const openChat = useCallback(
    (id: string) => {
      current.current = id;
      setConversationId(id);
      putChatInUrl(id);
      const cached = cachedChat(userId, id);
      setTurns(cached ? turnsFrom(cached) : []);
      void loadChat(id);
    },
    [userId, loadChat],
  );

  /** Clear the page for a new chat. It is saved when its first question is asked. */
  const newChat = useCallback(() => {
    current.current = null;
    setConversationId(null);
    setTurns([]);
    putChatInUrl(null);
  }, []);

  // On first load: fetch the chat named by ?c= (shown from the cache meanwhile), and the list.
  useEffect(() => {
    if (startId) {
      putChatInUrl(startId);
      void loadChat(startId);
    }
    void refreshList();
  }, [startId, loadChat, refreshList]);

  // Pick up changes from other tabs: on focus, on becoming visible, and when another tab writes the cache.
  useEffect(() => {
    const refresh = () => {
      void refreshList();
      if (current.current) void loadChat(current.current);
    };
    const onVisible = () => document.visibilityState === "visible" && refresh();
    const onStorage = (event: StorageEvent) => event.key === cacheKey(userId) && void refreshList();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("storage", onStorage);
    };
  }, [userId, refreshList, loadChat]);

  /** Replace one turn by id. */
  const update = useCallback((id: string, change: Partial<Turn>) => {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...change } : t)));
  }, []);

  /** Ask a question in the open chat, creating the chat first when it is new. */
  const send = useCallback(
    async (text: string, jobId: string, earlier: Turn[]) => {
      const question = text.trim();
      if (!question || controller.current) return;
      counter.current += 1;
      const id = `local-${counter.current}`;
      const abort = new AbortController();
      controller.current = abort;
      setTurns([...earlier, { id, question, jobId, state: "pending" }]);
      const history = historyFrom(earlier);
      try {
        let chatId = current.current;
        if (!chatId) {
          chatId = (await createConversation()).id;
          current.current = chatId;
          setConversationId(chatId);
          putChatInUrl(chatId);
        }
        const result = await ask(
          { question, conversation_id: chatId, ...(jobId ? { job_id: jobId } : {}), ...(history.length ? { history } : {}) },
          abort.signal,
        );
        update(id, { id: result.turn_id ?? id, state: "answered", result });
        setOpen((all) => (result.turn_id && all[id] ? { ...all, [result.turn_id]: all[id] } : all));
        void refreshList();
      } catch (error) {
        if (isAbort(error)) update(id, { state: "stopped" });
        else update(id, { state: "error", error: error instanceof ApiError ? error.message : "The assistant could not answer." });
      } finally {
        controller.current = null;
      }
    },
    [update, refreshList],
  );

  return {
    turns,
    waiting,
    conversations,
    conversationId,
    storage,
    /** Ask a new question at the end of the open chat. */
    ask: (text: string, jobId: string) => send(text, jobId, turns),
    /** Cancel the question being answered. */
    stop: () => controller.current?.abort(),
    /** Ask a stopped or failed question again. The old turn is removed and the new one goes at the end. */
    retry: (id: string) => {
      const index = turns.findIndex((t) => t.id === id);
      if (index >= 0) void send(turns[index].question, turns[index].jobId, [...turns.slice(0, index), ...turns.slice(index + 1)]);
    },
    openChat,
    newChat,
    /** Rename a saved chat and refresh the list. */
    rename: async (id: string, title: string) => {
      await renameConversation(id, title);
      await refreshList();
    },
    /** Delete a saved chat; if it was open, start an empty one. */
    remove: async (id: string) => {
      await deleteConversation(id);
      forgetChat(userId, id);
      if (current.current === id) newChat();
      await refreshList();
    },
    /** Whether a turn's evidence or trace panel is open. */
    isOpen: (id: string, panel: Panel) => (open[id] ?? []).includes(panel),
    /** Open or close one panel of one turn. Other turns keep their state. */
    toggle: (id: string, panel: Panel) =>
      setOpen((all) => {
        const now = all[id] ?? [];
        return { ...all, [id]: now.includes(panel) ? now.filter((p) => p !== panel) : [...now, panel] };
      }),
  };
}
