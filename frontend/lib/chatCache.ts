/**
 * A copy of the user's saved chats in localStorage, so a reload shows them at once while the
 * backend copy loads and then replaces them. It holds the chat list and the last few opened
 * chats, keyed by demo user. It only ever holds what the API returned to this user. Storage
 * can be blocked or full, so every read and write is wrapped and failure means "no cache".
 */

import type { Conversation, ConversationDetail } from "@/lib/types";

/** How many opened chats the cache keeps, most recent first. */
export const CACHED_CHATS = 10;

type Cache = { list: Conversation[]; chats: ConversationDetail[] };

/** The localStorage key for one demo user's cache. */
export function cacheKey(userId: string): string {
  return `recruitassist:chats:${userId}`;
}

/** The user's cache, or an empty one when there is none or storage cannot be read. */
function read(userId: string): Cache {
  try {
    const raw = window.localStorage.getItem(cacheKey(userId));
    const parsed = raw ? (JSON.parse(raw) as Cache) : null;
    return parsed && Array.isArray(parsed.list) && Array.isArray(parsed.chats) ? parsed : { list: [], chats: [] };
  } catch {
    return { list: [], chats: [] };
  }
}

/** Save the user's cache. Does nothing when storage is blocked or full. */
function write(userId: string, cache: Cache): void {
  try {
    window.localStorage.setItem(cacheKey(userId), JSON.stringify(cache));
  } catch {
    // Storage is blocked or full; the page keeps working from the backend.
  }
}

/** The cached chat list, newest first. */
export function cachedList(userId: string): Conversation[] {
  return read(userId).list;
}

/** Replace the cached chat list. */
export function cacheList(userId: string, list: Conversation[]): void {
  write(userId, { ...read(userId), list });
}

/** One cached chat with its turns, or null. */
export function cachedChat(userId: string, id: string): ConversationDetail | null {
  return read(userId).chats.find((c) => c.id === id) ?? null;
}

/** Remember an opened chat, keeping the CACHED_CHATS most recent. */
export function cacheChat(userId: string, chat: ConversationDetail): void {
  const cache = read(userId);
  write(userId, { ...cache, chats: [chat, ...cache.chats.filter((c) => c.id !== chat.id)].slice(0, CACHED_CHATS) });
}

/** Forget a deleted chat. */
export function forgetChat(userId: string, id: string): void {
  const cache = read(userId);
  write(userId, { list: cache.list.filter((c) => c.id !== id), chats: cache.chats.filter((c) => c.id !== id) });
}
