"use client";

/**
 * The frame around every signed-in page: the role's navigation on the left, a top bar with
 * who the demo user is and their scope, and the footer. Everything shown comes from
 * GET /api/me. Switching user changes the demo_user cookie and reloads the page. The
 * navigation can be collapsed to icons; each link keeps its name for screen readers and as a
 * hover title, and the choice is remembered in this browser.
 */

import { Badge, Button, DropdownMenu, IconButton } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Footer } from "@/components/Footer";
import { HowItWorks } from "@/components/HowItWorks";
import { NavIcon, SidebarIcon } from "@/components/Icons";
import { Logo } from "@/components/Logo";
import { getMe, getUsers } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { navFor, ROLE_LABELS } from "@/lib/roles";
import { useLoad } from "@/lib/useLoad";
import { usePreference } from "@/lib/usePreference";
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
  const [collapsed, setCollapsed] = usePreference("nav-collapsed", false);

  return (
    <div className={collapsed ? "shell shell-collapsed" : "shell"}>
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <nav className="shell-nav" aria-label="Main">
        <div className="shell-nav-top">
          <Link href="/dashboard" className="shell-brand" aria-label="RecruitAssist dashboard">
            <Logo size={28} withName={!collapsed} />
          </Link>
          <IconButton
            label={collapsed ? "Expand menu" : "Collapse menu"}
            title={collapsed ? "Expand menu" : "Collapse menu"}
            variant="ghost"
            size="sm"
            className="nav-toggle"
            aria-expanded={!collapsed}
            aria-controls="main-nav-links"
            onClick={() => setCollapsed(!collapsed)}
          >
            <SidebarIcon />
          </IconButton>
        </div>
        <div id="main-nav-links" className="nav-links">
          {role &&
            navFor(role).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="nav-link"
                title={collapsed ? item.label : undefined}
                aria-current={pathname === item.href || pathname.startsWith(`${item.href}/`) ? "page" : undefined}
              >
                <NavIcon name={item.icon} />
                <span className="nav-label">{item.label}</span>
              </Link>
            ))}
        </div>
      </nav>
      <div className="shell-main">
        <header className="topbar">
          {me.state === "ready" ? (
            <>
              <Badge tone="neutral">{ROLE_LABELS[me.data.user.role]}</Badge>
              <span className="topbar-name">{me.data.user.name}</span>
              <span className="tag" title="The jobs this user may see">
                Sees {me.data.summary.jobs} {me.data.summary.jobs === 1 ? "job" : "jobs"}
              </span>
              <span className="tag" title={`The data describes the pipeline as of ${me.data.scope.as_of}`}>
                Data as of {formatDate(me.data.scope.as_of)}
              </span>
            </>
          ) : (
            <span className="muted">{me.state === "error" ? "Could not load the current user." : "Loading user"}</span>
          )}
          <span className="topbar-spacer" />
          <HowItWorks />
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
