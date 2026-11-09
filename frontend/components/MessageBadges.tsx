/**
 * The small badges at the top of an answer: Verified or Unverified from the verifier, and
 * Recorded answer when a saved answer was shown in place of a live one. The reasons behind
 * them are under "Show evidence".
 */

import { Badge } from "@suseelkrishna/fieryfusion-react";
import type { AskResult } from "@/lib/types";

export function MessageBadges({ result }: { result: AskResult }) {
  return (
    <div className="message-badges">
      {result.verified ? <Badge tone="success">Verified</Badge> : <Badge tone="warning">Unverified</Badge>}
      {result.source === "recording" && <Badge tone="neutral">Recorded answer</Badge>}
    </div>
  );
}
