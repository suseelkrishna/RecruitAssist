"use client";

/**
 * "How it works", shown only when asked for: a link that opens a side drawer with the three
 * steps behind every answer and the principles the app follows. Used on the landing page and
 * in the app's top bar.
 */

import { Drawer, Stack } from "@suseelkrishna/fieryfusion-react";

const STEPS = [
  { title: "You ask", text: "Ask a question about your jobs, candidates, or tasks in plain English." },
  { title: "Tools compute the answer", text: "Read-only tools count and rank straight from the data. The AI never does the math." },
  { title: "The answer is checked and cited", text: "Every number and record ID is checked against the tool results, and each claim links to its source." },
];

const PRINCIPLES = [
  { title: "Read-only assistant", text: "The assistant can look things up but can never change a record." },
  { title: "Synthetic data", text: "Every person, job, and email here is invented. The company, Northbeam Robotics, is fictional." },
  { title: "People decide", text: "The assistant explains the pipeline. Hiring decisions are made by people." },
  { title: "Scoped by role", text: "Each role sees only its own jobs, and the server checks it on every request." },
];

export function HowItWorks({ label = "How it works" }: { label?: string }) {
  return (
    <Drawer
      title="How RecruitAssist works"
      description="Every number comes from the data, and every claim has a source."
      trigger={
        <button type="button" className="link-button">
          {label}
        </button>
      }
    >
      <Stack gap={20}>
        <section aria-labelledby="how-steps">
          <h3 id="how-steps">Three steps behind every answer</h3>
          <ol className="help-list">
            {STEPS.map((s) => (
              <li key={s.title}>
                <strong>{s.title}.</strong> <span className="muted">{s.text}</span>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="how-principles">
          <h3 id="how-principles">Principles</h3>
          <ul className="help-list">
            {PRINCIPLES.map((p) => (
              <li key={p.title}>
                <strong>{p.title}.</strong> <span className="muted">{p.text}</span>
              </li>
            ))}
          </ul>
        </section>
        <p className="muted">There are no passwords. Switching demo users is a demo feature, not real sign-in.</p>
      </Stack>
    </Drawer>
  );
}
