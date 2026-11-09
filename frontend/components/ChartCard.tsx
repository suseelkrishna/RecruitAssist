"use client";

/**
 * One dashboard chart: a title, the one-line takeaway written by the API, a "View as table"
 * switch that shows the same rows as a table, and an "Ask about this" link that opens /ask
 * with a question filled in. `info` explains how to read the chart, in an InfoTip after the
 * title. `chart` is the drawing; `controls` sit above it and `children` below it in both
 * views, so buttons stay reachable from the keyboard.
 */

import { ButtonLink, Card, DataTable, Switch } from "@suseelkrishna/fieryfusion-react";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";

export type TableView = { columns: string[]; rows: ReactNode[][] };

export function ChartCard({
  anchor,
  title,
  takeaway,
  question,
  table,
  empty,
  chart,
  controls,
  children,
  info,
}: {
  anchor: string;
  title: string;
  takeaway: string;
  question: string;
  table: TableView;
  empty?: boolean;
  chart?: ReactNode;
  controls?: ReactNode;
  children?: ReactNode;
  info?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  const headingId = useId();
  return (
    <Card id={anchor} aria-labelledby={headingId}>
      <HeadingWithInfo id={headingId} className="chart-title" title={title} info={info} />
      <p className="takeaway">{takeaway}</p>
      <div className="chart-actions">
        {!empty && <Switch label="View as table" checked={asTable} onCheckedChange={setAsTable} />}
        <ButtonLink as={Link} href={`/ask?q=${encodeURIComponent(question)}`} variant="ghost" size="sm">
          Ask about this
        </ButtonLink>
      </div>
      {empty ? (
        <p className="muted">No data for these filters.</p>
      ) : (
        <>
          {controls}
          {asTable ? (
            <DataTable caption={title} columns={table.columns} rows={table.rows} />
          ) : (
            chart && (
              <div className="chart-box" role="img" aria-label={`${title}. ${takeaway} Switch on View as table for the numbers.`}>
                {chart}
              </div>
            )
          )}
          {children}
        </>
      )}
    </Card>
  );
}
