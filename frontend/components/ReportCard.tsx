/**
 * One report card on the Quality page. When the report has not been produced yet, the card
 * says "Not available" and an InfoTip gives the reason, so a card is never blank. `info`
 * explains the report in an InfoTip after the title.
 */

import { Card } from "@suseelkrishna/fieryfusion-react";
import type { ReactNode } from "react";
import { InfoTip } from "@/components/InfoTip";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

export function ReportCard({ title, value, reason, info, children }: {
  title: string;
  value: unknown;
  reason: string | undefined;
  info?: string;
  children: ReactNode;
}) {
  return (
    <Card className="quality-card">
      <HeadingWithInfo as="h3" title={title} info={info} />
      {value === null || value === undefined ? (
        <p style={{ margin: 0 }}>
          <span className="muted">Not available</span>
          <InfoTip title={title}>{reason ?? "This report has not been produced yet."}</InfoTip>
        </p>
      ) : (
        children
      )}
    </Card>
  );
}
