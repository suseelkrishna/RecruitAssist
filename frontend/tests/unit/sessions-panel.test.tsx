/**
 * The saved chats panel: newest first as given, the open chat marked, Rename and Delete from
 * each chat's "More actions" menu (delete only after confirming), an empty state, and the
 * memory warning for admin only.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SessionsPanel } from "@/components/SessionsPanel";
import type { Conversation } from "@/lib/types";

const CHATS: Conversation[] = [
  { id: "CONV-bbbbbbbbbbbb", title: "Newer chat", created_at: "2026-11-09T16:00:00Z", updated_at: "2026-11-09T17:00:00Z", turn_count: 2 },
  { id: "CONV-aaaaaaaaaaaa", title: "Older chat", created_at: "2026-11-08T16:00:00Z", updated_at: "2026-11-08T17:00:00Z", turn_count: 1 },
];

/** Render the panel with spies for every action. */
function renderPanel(overrides: Partial<Parameters<typeof SessionsPanel>[0]> = {}) {
  const props = {
    conversations: CHATS, currentId: "CONV-aaaaaaaaaaaa", role: "hr_user" as const,
    onNew: vi.fn(), onOpen: vi.fn(), onRename: vi.fn(async () => {}), onDelete: vi.fn(), ...overrides,
  };
  render(<SessionsPanel {...props} />);
  return props;
}

describe("SessionsPanel", () => {
  it("lists chats in the order given, newest first, and marks the open one", async () => {
    const props = renderPanel();
    const items = within(screen.getByRole("navigation", { name: "Saved chats" })).getAllByRole("listitem");
    expect(items.map((li) => li.querySelector(".session-title")?.textContent)).toEqual(["Newer chat", "Older chat"]);
    expect(screen.getByRole("button", { name: /^Older chat/ }).getAttribute("aria-current")).toBe("true");
    expect(screen.getByRole("button", { name: /^Newer chat/ }).getAttribute("aria-current")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /^Newer chat/ }));
    expect(props.onOpen).toHaveBeenCalledWith("CONV-bbbbbbbbbbbb");
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(props.onNew).toHaveBeenCalled();
  });

  it("renames inline and saves with Enter", async () => {
    const props = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "More actions for Newer chat" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const field = screen.getByLabelText("New name for Newer chat");
    await waitFor(() => expect(document.activeElement).toBe(field));
    await userEvent.clear(field);
    await userEvent.type(field, "Offers this week{Enter}");
    expect(props.onRename).toHaveBeenCalledWith("CONV-bbbbbbbbbbbb", "Offers this week");
  });

  it("deletes only after the confirmation", async () => {
    const props = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "More actions for Older chat" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const confirm = screen.getByRole("group", { name: "Delete Older chat?" });
    expect(props.onDelete).not.toHaveBeenCalled();
    await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
    expect(props.onDelete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "More actions for Older chat" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Delete Older chat?" })).getByRole("button", { name: "Delete" }));
    expect(props.onDelete).toHaveBeenCalledWith("CONV-aaaaaaaaaaaa");
  });

  it("has an InfoTip after its heading", () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: "Saved chats" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "About Saved chats" })).toBeTruthy();
  });

  it("shows an empty state", () => {
    renderPanel({ conversations: [], currentId: null });
    expect(screen.getByText(/No saved chats yet/)).toBeTruthy();
  });

  it("warns admin, and only admin, when chats are kept in memory", () => {
    renderPanel({ role: "admin", storage: "memory" });
    expect(screen.getByText(/reset when the server restarts/)).toBeTruthy();
  });

  it("does not warn other roles or when Redis is used", () => {
    renderPanel({ role: "hr_manager", storage: "memory" });
    expect(screen.queryByText(/reset when the server restarts/)).toBeNull();
  });
});
