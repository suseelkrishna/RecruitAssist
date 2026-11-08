"use client";

/**
 * The frame around every signed-in page: the role's navigation on the left, a top bar with
 * who the demo user is and their scope, and the footer. Everything shown comes from
 * GET /api/me. Switching user changes the demo_user cookie and reloads the page.
 */

import { Badge, Button, DropdownMenu } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Footer } from "@/components/Footer";
import { getMe, getUsers } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { navFor, ROLE_LABELS } from "@/lib/roles";
import { useLoad } from "@/lib/useLoad";
import { setDemoUser } from "@/lib/user";

/** Change the demo user and reload, so every panel refetches as the new user. */
function switchTo(userId: string) {
  setDemoUser(userId);
  window.location.reload();
}

export function AppShell({ children }: { children: ReactNode }) {
  const me = useLoad(getMe, "me");
  const users = useLoad(getUsers, "users");
  const pathname = usePathname();
  const role = me.state === "ready" ? me.data.user.role : null;

  return (
    <div className="shell">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <nav className="shell-nav" aria-label="Main">
        <Link href="/dashboard" className="shell-brand">
          RecruitAssist
        </Link>
        {role &&
          navFor(role).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="nav-link"
              aria-current={pathname === item.href || pathname.startsWith(`${item.href}/`) ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
      </nav>
      <div className="shell-main">
        <header className="topbar">
          {me.state === "ready" ? (
            <>
              <Badge tone="neutral">{ROLE_LABELS[me.data.user.role]}</Badge>
              <span className="topbar-name">{me.data.user.name}</span>
              <span className="chip" title="Jobs this user may see">
                Scope: {me.data.summary.jobs} jobs
              </span>
              <span className="chip" title="The time the data describes">
                Data as of {formatDateTime(me.data.scope.as_of)}
              </span>
            </>
          ) : (
            <span className="muted">{me.state === "error" ? "Could not load the current user." : "Loading user"}</span>
          )}
          <span className="topbar-spacer" />
          <DropdownMenu
            trigger={
              <Button variant="secondary" size="sm">
                Switch user
              </Button>
            }
            items={
              users.state === "ready"
                ? users.data.users.map((u) => ({
                    label: `${u.name}, ${ROLE_LABELS[u.role]}`,
                    onSelect: () => switchTo(u.user_id),
                    disabled: me.state === "ready" && me.data.user.user_id === u.user_id,
                  }))
                : [{ label: "Loading users", onSelect: () => undefined, disabled: true }]
            }
          />
        </header>
        <main id="content" className="content fade-in">
          {children}
        </main>
        <Footer />
      </div>
    </div>
  );
}
