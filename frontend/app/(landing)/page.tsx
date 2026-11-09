"use client";

/**
 * The landing page: the RecruitAssist mark, one line on what it does, and the demo users to
 * pick from (GET /api/users). Picking one sets the demo_user cookie and opens the dashboard.
 * The longer explanation is one click away under "How it works".
 */

import { Avatar } from "@suseelkrishna/fieryfusion-react";
import { useRouter } from "next/navigation";
import { Footer } from "@/components/Footer";
import { HowItWorks } from "@/components/HowItWorks";
import { Logo } from "@/components/Logo";
import { Empty, ErrorState } from "@/components/PageStates";
import { getUsers } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/roles";
import type { DemoUser, Role } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { setDemoUser } from "@/lib/user";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

const ROLE_ORDER: Role[] = ["admin", "hr_manager", "hr_user"];

/** One demo user as a tile: initials, name, and role. */
function UserTile({ user, onPick }: { user: DemoUser; onPick: (user: DemoUser) => void }) {
  const label = `${user.name}, ${ROLE_LABELS[user.role]}`;
  return (
    <button type="button" className="user-tile" aria-label={label} onClick={() => onPick(user)}>
      <Avatar name={user.name} size="sm" />
      <span className="user-tile-text">
        <span className="user-tile-name">{user.name}</span>
        <span className="user-tile-role">{ROLE_LABELS[user.role]}</span>
      </span>
    </button>
  );
}

export default function LandingPage() {
  const users = useLoad(getUsers, "users");
  const router = useRouter();

  /** Remember the picked user and open their dashboard. */
  function pick(user: DemoUser) {
    setDemoUser(user.user_id);
    router.push("/dashboard");
  }

  const sorted =
    users.state === "ready"
      ? [...users.data.users].sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role))
      : [];

  return (
    <div className="landing-page">
      <main className="landing-panel fade-in" id="content">
        <Logo size={48} />
        <h1>RecruitAssist</h1>
        <p className="landing-tagline">Ask your hiring pipeline anything.</p>

        <HeadingWithInfo
          id="pick"
          className="landing-pick"
          title="Choose a demo user"
          info="A fictional company, Northbeam Robotics. There are no passwords; switching users is a demo feature, not sign-in."
        />
        {users.state === "loading" && (
          <p role="status" className="muted">
            Loading demo users
          </p>
        )}
        {(users.state === "error" || users.state === "not_found") && (
          <ErrorState message={users.state === "error" ? users.message : "Demo users could not be loaded."} onRetry={users.reload} />
        )}
        {users.state === "ready" && sorted.length === 0 && (
          <Empty title="No demo users" description="The backend returned no demo users." />
        )}
        {sorted.length > 0 && (
          <ul className="user-tiles list-plain" aria-labelledby="pick">
            {sorted.map((u) => (
              <li key={u.user_id}>
                <UserTile user={u} onPick={pick} />
              </li>
            ))}
          </ul>
        )}

        <HowItWorks />
      </main>
      <Footer />
    </div>
  );
}
