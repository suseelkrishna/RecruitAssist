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
        <p className="landing-tagline">Ask your hiring pipeline anything. Every number comes from the data.</p>

        <h2 id="pick" className="landing-pick">
          Choose a demo user
        </h2>
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

        <p className="landing-note">
          A fictional company, Northbeam Robotics. No passwords; switching users is a demo feature.
        </p>
        <HowItWorks />
      </main>
      <Footer />
    </div>
  );
}
