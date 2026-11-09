/** The verifier's result for one answer: Verified, or Needs review with the reasons it gave. */

import { StatusPill } from "@suseelkrishna/fieryfusion-react";
import type { AskResult } from "@/lib/types";

export function VerifierBadge({ result }: { result: AskResult }) {
  if (result.verified) return <StatusPill tone="success">Verified</StatusPill>;
  const reasons = result.verifier?.failures ?? [];
  return (
    <div>
      <StatusPill tone="warning">Needs review</StatusPill>
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
