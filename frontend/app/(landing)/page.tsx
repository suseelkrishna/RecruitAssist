"use client";

/**
 * The landing page: what the assistant does, the principles it follows, and the demo users
 * to pick from (GET /api/users). Picking one sets the demo_user cookie and opens the dashboard.
 */

import { Button, Card } from "@suseelkrishna/fieryfusion-react";
import { useRouter } from "next/navigation";
import { Footer } from "@/components/Footer";
import { ErrorState, Empty } from "@/components/PageStates";
import { getUsers } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/roles";
import type { DemoUser, Role } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { setDemoUser } from "@/lib/user";

const STEPS = [
  { title: "You ask", text: "Ask a question about your jobs, candidates, or tasks in plain English." },
  { title: "Tools compute the answer", text: "Read-only tools count and rank straight from the data. The AI never does the math." },
  { title: "The answer is checked and cited", text: "Every number and record ID is checked against the tool results, and each claim links to its source." },
];

const PRINCIPLES = [
  { title: "Read-only assistant", text: "The assistant can look things up but can never change a record." },
  { title: "Synthetic data", text: "Every person, job, and email here is invented." },
  { title: "People decide", text: "The assistant explains the pipeline. Hiring decisions are made by people." },
  { title: "Scoped by role", text: "Each role sees only its own jobs, and the server enforces it on every request." },
];

const ROLE_ORDER: Role[] = ["admin", "hr_manager", "hr_user"];
const GROUP_TITLES: Record<Role, string> = { admin: "Admin", hr_manager: "HR Managers", hr_user: "HR Users" };

export default function LandingPage() {
  const users = useLoad(getUsers, "users");
  const router = useRouter();

  /** Remember the picked user and open their dashboard. */
  function pick(user: DemoUser) {
    setDemoUser(user.user_id);
    router.push("/dashboard");
  }

  return (
    <>
      <main className="landing fade-in" id="content">
        <p className="label-small">RecruitAssist</p>
        <h1>Ask your hiring pipeline anything. Every number comes from the data, every claim has a source.</h1>

        <section aria-labelledby="how">
          <h2 id="how">How it works</h2>
          <ol className="grid grid-3 list-plain">
            {STEPS.map((step, i) => (
              <li key={step.title}>
                <Card>
                  <p className="step-number">Step {i + 1}</p>
                  <h3>{step.title}</h3>
                  <p className="muted">{step.text}</p>
                </Card>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="principles">
          <h2 id="principles">Principles</h2>
          <ul className="grid grid-3 list-plain">
            {PRINCIPLES.map((p) => (
              <li key={p.title}>
                <Card title={p.title} description={p.text} />
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="pick">
          <h2 id="pick">Pick a demo user</h2>
          <p className="muted">
            This demo uses a fictional company, Northbeam Robotics. There are no passwords. Switching users is a demo
            feature, not real sign-in.
          </p>
          {users.state === "loading" && <p role="status">Loading demo users</p>}
          {users.state === "error" && <ErrorState message={users.message} onRetry={users.reload} />}
          {users.state === "ready" && users.data.users.length === 0 && (
            <Empty title="No demo users" description="The backend returned no demo users." />
          )}
          {users.state === "ready" &&
            ROLE_ORDER.map((role) => {
              const group = users.data.users.filter((u) => u.role === role);
              if (group.length === 0) return null;
              return (
                <div className="user-group" key={role}>
                  <h3>{GROUP_TITLES[role]}</h3>
                  <div className="card-actions">
                    {group.map((u) => (
                      <Button key={u.user_id} variant="secondary" onClick={() => pick(u)}>
                        {u.name}, {ROLE_LABELS[u.role]}
                      </Button>
                    ))}
                  </div>
                </div>
              );
            })}
        </section>
      </main>
      <Footer />
    </>
  );
}
