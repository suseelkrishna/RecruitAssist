/**
 * Labels and navigation by role. Hiding a link is a convenience only: the backend still
 * checks access on every route and answers 404 or 403 when a role may not see something.
 */

import type { IconName } from "@/components/Icons";
import type { Role } from "@/lib/types";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  hr_manager: "HR Manager",
  hr_user: "HR User",
};

export type NavItem = { href: string; label: string; icon: IconName };

const ALL: (NavItem & { roles: Role[] })[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/ask", label: "Ask", icon: "ask", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/jobs", label: "Jobs", icon: "jobs", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/tasks", label: "Tasks", icon: "tasks", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/sources", label: "Sources", icon: "sources", roles: ["admin", "hr_manager"] },
  { href: "/changes", label: "Changes", icon: "changes", roles: ["admin", "hr_manager"] },
  { href: "/quality", label: "Quality", icon: "quality", roles: ["admin"] },
];

/** The left navigation items this role may use, in display order. */
export function navFor(role: Role): NavItem[] {
  return ALL.filter((item) => item.roles.includes(role)).map(({ href, label, icon }) => ({ href, label, icon }));
}

/** True when the role may see the recruiter filter and the recruiter load chart. */
export function seesRecruiters(role: Role): boolean {
  return role === "admin" || role === "hr_manager";
}
