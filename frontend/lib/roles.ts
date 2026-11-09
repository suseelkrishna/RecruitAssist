/**
 * Labels and navigation by role. Hiding a link is a convenience only: the backend still
 * checks access on every route and answers 404 or 403 when a role may not see something.
 */

import type { Role } from "@/lib/types";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  hr_manager: "HR Manager",
  hr_user: "HR User",
};

export type NavItem = { href: string; label: string };

const ALL: (NavItem & { roles: Role[] })[] = [
  { href: "/dashboard", label: "Dashboard", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/ask", label: "Ask", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/jobs", label: "Jobs", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/tasks", label: "Tasks", roles: ["admin", "hr_manager", "hr_user"] },
  { href: "/sources", label: "Sources", roles: ["admin", "hr_manager"] },
  { href: "/changes", label: "Changes", roles: ["admin", "hr_manager"] },
  { href: "/quality", label: "Quality", roles: ["admin"] },
];

/** The left navigation items this role may use, in display order. */
export function navFor(role: Role): NavItem[] {
  return ALL.filter((item) => item.roles.includes(role)).map(({ href, label }) => ({ href, label }));
}

/** True when the role may see the recruiter filter and the recruiter load chart. */
export function seesRecruiters(role: Role): boolean {
  return role === "admin" || role === "hr_manager";
}
