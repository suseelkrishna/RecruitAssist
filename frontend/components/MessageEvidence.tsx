"use client";

/**
 * The parts of an answer that are hidden until asked for. "Show evidence" lists the cited
 * records, the time the data is as of, the model, and the note on a recorded answer. For admin
 * only, "Show trace" opens the behind the scenes panel. Each button says whether its panel is
 * open (aria-expanded) and which panel it controls (aria-controls).
 */

import { Button } from "@suseelkrishna/fieryfusion-react";
import { BehindTheScenes } from "@/components/BehindTheScenes";
import { CitationChip } from "@/components/CitationChip";
import { formatDateTime } from "@/lib/format";
import type { AskResult, Role } from "@/lib/types";
import type { Panel } from "@/lib/useChat";

/** Why a recorded answer was shown in place of a live one. */
export function recordingNote(result: AskResult): string {
  return result.recording_reason === "live_unavailable"
    ? "Showing a recorded answer because live answers are not available right now."
    : "Showing a recorded answer because the live limit was reached.";
}

export function MessageEvidence({ id, result, role, isOpen, onToggle }: {
  id: string;
  result: AskResult;
  role: Role;
  isOpen: (panel: Panel) => boolean;
  onToggle: (panel: Panel) => void;
}) {
  const evidenceId = `${id}-evidence`;
  const traceId = `${id}-trace`;
  const reasons = result.verifier?.failures ?? [];
  return (
    <div className="message-evidence">
      <div className="message-toggles">
        <Button variant="ghost" size="sm" aria-expanded={isOpen("evidence")} aria-controls={evidenceId} onClick={() => onToggle("evidence")}>
          {isOpen("evidence") ? "Hide evidence" : "Show evidence"}
        </Button>
        {role === "admin" && (
          <Button variant="ghost" size="sm" aria-expanded={isOpen("trace")} aria-controls={traceId} onClick={() => onToggle("trace")}>
            {isOpen("trace") ? "Hide trace" : "Show trace"}
          </Button>
        )}
      </div>
      <div id={evidenceId} className="message-panel" hidden={!isOpen("evidence")}>
          {result.source === "recording" && (
            <p>
              {recordingNote(result)} Recorded {formatDateTime(result.recorded_at)}.
            </p>
          )}
          <p className="label-small">Records cited</p>
          {result.citations.length > 0 ? (
            <div className="chips">
              {result.citations.map((cited) => (
                <CitationChip key={cited} id={cited} />
              ))}
            </div>
          ) : (
            <p className="muted">This answer cites no records.</p>
          )}
          {reasons.length > 0 && (
            <>
              <p className="label-small">Why it needs review</p>
              <ul>
                {reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </>
          )}
          <dl className="kv">
            <dt>Data as of</dt>
            <dd>{formatDateTime(result.as_of)}</dd>
            <dt>Model</dt>
            <dd className="mono">{result.model ?? "No data"}</dd>
          </dl>
      </div>
      {role === "admin" && (
        <div id={traceId} className="message-panel" hidden={!isOpen("trace")}>
          <BehindTheScenes result={result} />
        </div>
      )}
    </div>
  );
}
