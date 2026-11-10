/**
 * The Ask conversation against a stubbed backend: Enter sends and Shift+Enter does not, Stop
 * aborts and offers Retry, Retry asks again, a follow-up carries the earlier turn with its
 * citations, evidence panels keep their state per message, and only admin gets the trace.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AskPage from "@/app/ask/page";
import type { AskResult, Role } from "@/lib/types";

// The page's query string; a test that opens a saved chat sets ?c= here.
let search = new URLSearchParams();

vi.mock("next/navigation", () => ({
  usePathname: () => "/ask",
  useSearchParams: () => search,
  notFound: () => {
    throw new Error("not found");
  },
}));

/** An answer citing the given record IDs. */
function answer(text: string, citations: string[]): AskResult {
  return {
    answer: text, status: "answered", verified: true, label: "verified", citations,
    model: "claude-haiku-5-5", as_of: "2026-11-09T17:00:00Z", job_id: null, source: "live",
  };
}

type AskCall = { body: Record<string, unknown>; signal?: AbortSignal | null };

const CHAT_ID = "CONV-aaaaaaaaaaaa";

/**
 * Stub fetch for /api/me, /api/users, /api/conversations, and /api/ask. `reply` decides each
 * /api/ask response; returning null leaves the request waiting until it is aborted. Every
 * request is recorded in `calls` as "METHOD url".
 */
function stubBackend(role: Role, reply: (n: number) => AskResult | null, calls: string[] = []): AskCall[] {
  const asks: AskCall[] = [];
  const me = {
    user: { user_id: "USR-9", name: "Test User", role },
    allowed_job_ids: ["JOB-1"], team_ids: [],
    summary: { jobs: 1, active_candidates: 4, overdue_tasks: 1 },
    scope: { as_of: "2026-11-09T17:00:00Z", role, jobs: [{ job_id: "JOB-1", title: "Controls Engineer" }], overdue_items: 1 },
  };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    calls.push(`${init.method ?? "GET"} ${url}`);
    if (url === "/api/me") return json(me);
    if (url === "/api/users") return json({ users: [] });
    if (url === "/api/conversations" && init.method === "POST")
      return json({ id: CHAT_ID, title: "New chat", created_at: "2026-11-09T17:00:00Z", updated_at: "2026-11-09T17:00:00Z", turn_count: 0 });
    if (url === "/api/conversations") return json({ conversations: [] });
    if (url.startsWith("/api/conversations/")) return json({ id: CHAT_ID, title: "Chat", created_at: "", updated_at: "", turn_count: 0, turns: [] });
    asks.push({ body: JSON.parse(String(init.body)), signal: init.signal });
    const result = reply(asks.length);
    if (result) return json(result);
    return new Promise<Response>((_, reject) =>
      init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))));
  }));
  return asks;
}

/** The question box, once the page has loaded the user. */
async function box() {
  return screen.findByLabelText("Your question");
}

/** Render the Ask page and a user-event session. */
function setup() {
  render(<AskPage />);
  return userEvent.setup();
}

describe("Ask conversation", () => {
  it("sends on Enter, adds a line on Shift+Enter, and returns focus to the box", async () => {
    const asks = stubBackend("hr_user", () => answer("Two tasks are overdue.", []));
    const user = setup();
    const input = await box();
    await user.type(input, "First line{Shift>}{Enter}{/Shift}second line");
    expect(asks).toHaveLength(0);
    expect((input as HTMLTextAreaElement).value).toBe("First line\nsecond line");
    await user.type(input, "{Enter}");
    expect(await screen.findByText("Two tasks are overdue.")).toBeTruthy();
    expect(asks).toHaveLength(1);
    expect(asks[0].body.question).toBe("First line\nsecond line");
    expect(document.activeElement).toBe(input);
    expect(screen.getByRole("log")).toBeTruthy();
  });

  it("Stop aborts the request and Retry asks again", async () => {
    const asks = stubBackend("hr_user", (n) => (n === 1 ? null : answer("Here is the answer.", [])));
    const user = setup();
    await user.type(await box(), "What is overdue?{Enter}");
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByText("Stopped.")).toBeTruthy();
    expect(asks[0].signal?.aborted).toBe(true);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Here is the answer.")).toBeTruthy();
    expect(asks).toHaveLength(2);
    expect(asks[1].body.question).toBe("What is overdue?");
    expect(screen.queryByText("Stopped.")).toBeNull();
  });

  it("sends the earlier turn with its citations as history, but not a stopped turn", async () => {
    const asks = stubBackend("hr_user", (n) => (n === 2 ? null : answer(`Answer ${n} [APP-062].`, ["APP-062", "TASK-011"])));
    const user = setup();
    await user.type(await box(), "Who is waiting on me?{Enter}");
    await screen.findByText(/Answer 1/);
    await user.type(await box(), "Stopped question{Enter}");
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    await screen.findByText("Stopped.");
    await user.type(await box(), "And the oldest one?{Enter}");
    await screen.findByText(/Answer 3/);
    expect(asks[0].body.history).toBeUndefined();
    expect(asks[2].body.history).toEqual([
      { question: "Who is waiting on me?", answer: "Answer 1 [APP-062].", citations: ["APP-062", "TASK-011"] },
    ]);
  });

  it("Show evidence toggles per message and keeps its state when new messages arrive", async () => {
    stubBackend("hr_user", (n) => answer(`Answer ${n}.`, [`TASK-01${n}`]));
    const user = setup();
    await user.type(await box(), "First?{Enter}");
    await screen.findByText("Answer 1.");
    const first = screen.getByText("Answer 1.").closest("li")!;
    const toggle = within(first).getByRole("button", { name: "Show evidence" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const panel = document.getElementById(toggle.getAttribute("aria-controls")!)!;
    expect(panel.hidden).toBe(true);
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.hidden).toBe(false);
    expect(within(panel).getByText("TASK-011")).toBeTruthy();
    await user.type(await box(), "Second?{Enter}");
    await screen.findByText("Answer 2.");
    expect(within(first).getByRole("button", { name: "Hide evidence" }).getAttribute("aria-expanded")).toBe("true");
    const second = screen.getByText("Answer 2.").closest("li")!;
    expect(within(second).getByRole("button", { name: "Show evidence" }).getAttribute("aria-expanded")).toBe("false");
  });

  it("shows the trace toggle to admin only", async () => {
    stubBackend("admin", () => ({ ...answer("Admin answer.", []), steps: [{ tool: "list_jobs", input: {}, rows: 7 }] }));
    const user = setup();
    await user.type(await box(), "Pipeline?{Enter}");
    await screen.findByText("Admin answer.");
    await user.click(screen.getByRole("button", { name: "Show trace" }));
    expect(screen.getByRole("button", { name: "Hide trace" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("list_jobs")).toBeTruthy();
  });

  it("has no trace toggle for an HR User", async () => {
    stubBackend("hr_user", () => answer("User answer.", []));
    const user = setup();
    await user.type(await box(), "Tasks?{Enter}");
    await screen.findByText("User answer.");
    expect(screen.queryByRole("button", { name: /trace/ })).toBeNull();
    await waitFor(() => expect(screen.getByText("Verified")).toBeTruthy());
  });
});

describe("Saved chats", () => {
  it("creates the chat on the first send, then asks with its conversation_id", async () => {
    const calls: string[] = [];
    const asks = stubBackend("hr_user", () => answer("Saved answer.", []), calls);
    const user = setup();
    await user.type(await box(), "What is overdue?{Enter}");
    await screen.findByText("Saved answer.");
    const create = calls.indexOf("POST /api/conversations");
    const asked = calls.indexOf("POST /api/ask");
    expect(create).toBeGreaterThanOrEqual(0);
    expect(asked).toBeGreaterThan(create);
    expect(asks[0].body.conversation_id).toBe(CHAT_ID);
    expect(new URL(window.location.href).searchParams.get("c")).toBe(CHAT_ID);
    await user.type(await box(), "And next?{Enter}");
    await screen.findAllByText("Saved answer.");
    expect(calls.filter((c) => c === "POST /api/conversations")).toHaveLength(1);
  });

  it("opens on a new chat, not the newest saved one", async () => {
    const saved = { id: "CONV-cccccccccccc", title: "Yesterday's chat", created_at: "2026-11-08T16:00:00Z", updated_at: "2026-11-08T16:00:00Z", turn_count: 1 };
    const calls: string[] = [];
    stubBackend("hr_user", () => answer("Unused.", []), calls);
    const fetchStub = vi.mocked(fetch);
    const original = fetchStub.getMockImplementation()!;
    fetchStub.mockImplementation(async (url, init) =>
      url === "/api/conversations" && !init?.method
        ? new Response(JSON.stringify({ conversations: [saved] }), { status: 200, headers: { "Content-Type": "application/json" } })
        : original(url, init));
    setup();
    expect(await screen.findByRole("heading", { name: "What would you like to know?" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: /^Yesterday's chat/ })).toBeTruthy();
    expect(calls.some((c) => c.startsWith("GET /api/conversations/"))).toBe(false);
    expect(screen.queryByRole("log")).toBeNull();
    expect(screen.getByRole("region", { name: "Try one of these" })).toBeTruthy();
  });

  it("shows the user's initials beside a question and RecruitBot beside the reply", async () => {
    stubBackend("hr_user", () => answer("Two tasks are overdue.", []));
    const user = setup();
    await user.type(await box(), "What is overdue?{Enter}");
    const turn = (await screen.findByText("Two tasks are overdue.")).closest("li")!;
    expect(turn.querySelector(".chat-row-user .ff-avatar")?.textContent).toBe("TU");
    expect(turn.querySelector(".chat-row-assistant svg.recruitbot")).toBeTruthy();
  });

  it("shows the cached chat before the backend answers", async () => {
    search = new URLSearchParams("c=CONV-bbbbbbbbbbbb");
    const cached = { id: "CONV-bbbbbbbbbbbb", title: "Cached chat", created_at: "2026-11-09T16:00:00Z", updated_at: "2026-11-09T16:00:00Z", turn_count: 1 };
    window.localStorage.setItem("recruitassist:chats:USR-9", JSON.stringify({
      list: [cached],
      chats: [{ ...cached, turns: [{ ...answer("From the cache.", []), turn_id: "TURN-1", at: "2026-11-09T16:00:00Z", question: "Cached question" }] }],
    }));
    document.cookie = "demo_user=USR-9; path=/";
    const me = { user: { user_id: "USR-9", name: "Test User", role: "hr_user" }, allowed_job_ids: [], team_ids: [],
      summary: { jobs: 0, active_candidates: 0, overdue_tasks: 0 }, scope: { as_of: "2026-11-09T17:00:00Z", role: "hr_user", jobs: [], overdue_items: 0 } };
    // /api/me answers; the chat routes never do, so anything shown came from the cache.
    vi.stubGlobal("fetch", vi.fn((url: string) =>
      url === "/api/me" ? Promise.resolve(new Response(JSON.stringify(me), { status: 200 })) : new Promise<Response>(() => {})));
    render(<AskPage />);
    expect(await screen.findByText("From the cache.")).toBeTruthy();
    expect(screen.getAllByText("Cached chat").length).toBeGreaterThan(0);
    window.localStorage.clear();
    search = new URLSearchParams();
  });

  it("works when storage is blocked", async () => {
    const blocked = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    const spies = [vi.spyOn(Storage.prototype, "getItem").mockImplementation(blocked),
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(blocked)];
    const asks = stubBackend("hr_user", () => answer("Still works.", []));
    const user = setup();
    await user.type(await box(), "What is overdue?{Enter}");
    expect(await screen.findByText("Still works.")).toBeTruthy();
    expect(asks[0].body.conversation_id).toBe(CHAT_ID);
    spies.forEach((s) => s.mockRestore());
  });
});
