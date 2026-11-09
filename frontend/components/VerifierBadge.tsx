/** The verifier's result for one answer: Verified, or Needs review with the reasons it gave. */

import { StatusPill } from "@suseelkrishna/fieryfusion-react";
import type { AskResult } from "@/lib/types";

export function VerifierBadge({ result }: { result: AskResult }) {
  if (result.verified)
    return (
      <div>
        <StatusPill tone="success">Verified</StatusPill>{" "}
        <span className="muted">Every number and record ID in this answer matches the data.</span>
      </div>
    );
  const reasons = result.verifier?.failures ?? [];
  return (
    <div>
      <StatusPill tone="warning">Needs review</StatusPill>{" "}
      <span className="muted">Part of this answer could not be matched to the data. Check it before relying on it.</span>
      {reasons.length > 0 && (
        <ul>
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
