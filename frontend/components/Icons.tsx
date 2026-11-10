/**
 * Small line icons for the navigation and the Ask page, drawn here so the app needs no icon
 * package. Each one is 20 by 20, uses the current text color, and is hidden from screen
 * readers, because the control it sits in always has its own text label.
 */

import type { ReactNode } from "react";

/** The shared frame: a 24 unit grid with 1.8 unit strokes and rounded ends. */
function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export type IconName = "dashboard" | "ask" | "jobs" | "tasks" | "sources" | "changes" | "quality";

const PATHS: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="8" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="5" rx="1.5" />
      <rect x="13.5" y="11.5" width="7" height="9" rx="1.5" />
      <rect x="3.5" y="14.5" width="7" height="6" rx="1.5" />
    </>
  ),
  ask: (
    <>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z" />
      <path d="M8.5 8h7M8.5 11.5h4.5" />
    </>
  ),
  jobs: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3 12.5h18" />
    </>
  ),
  tasks: (
    <>
      <path d="M4 6.5l1.5 1.5L8.5 5M4 12.5l1.5 1.5 3-3M4 18.5l1.5 1.5 3-3" />
      <path d="M12 6.5h8M12 12.5h8M12 18.5h8" />
    </>
  ),
  sources: (
    <>
      <path d="M9 3v5M15 3v5M6.5 8h11v3a5.5 5.5 0 0 1-11 0z" />
      <path d="M12 16.5V21" />
    </>
  ),
  changes: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" />
      <path d="M3.5 3.5V8H8M12 7.5V12l3 2" />
    </>
  ),
  quality: (
    <>
      <path d="M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </>
  ),
};

/** The icon for one navigation item. */
export function NavIcon({ name }: { name: IconName }) {
  return <Icon>{PATHS[name]}</Icon>;
}

/** A panel with a bar down its left side: the "collapse or expand the menu" control. */
export function SidebarIcon() {
  return (
    <Icon>
      <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
      <path d="M9.5 4v16" />
    </Icon>
  );
}

/** A plus inside a speech bubble, for New chat. */
export function NewChatIcon() {
  return (
    <Icon size={18}>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z" />
      <path d="M12 6.5v6M9 9.5h6" />
    </Icon>
  );
}

/** A small right arrow that tells a card it can be opened. */
export function ArrowIcon() {
  return (
    <Icon size={16}>
      <path d="M5 12h13M13 6.5L18.5 12 13 17.5" />
    </Icon>
  );
}
