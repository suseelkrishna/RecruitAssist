"use client";

/**
 * What happened to produce an answer: each tool called with its input and the rows it
 * returned, then tokens, cache hits, latency, and estimated cost, all as the API reports them.
 * The Ask page shows it to admin only, under "Show trace", and the API sends these fields only to admin.
 */

import { DataTable } from "@suseelkrishna/fieryfusion-react";
import { formatDateTime, show } from "@/lib/format";
import { toolName } from "@/lib/tools";
import type { AskResult } from "@/lib/types";

export function BehindTheScenes({ result }: { result: AskResult }) {
  const usage = result.usage;
  return (
    <>
      <DataTable
        caption="Tools called"
        columns={["Tool", "Input", "Rows returned", "Time"]}
        rows={(result.steps ?? []).map((s) => [
          <span key="tool">
            {toolName(s.tool)} <span className="mono muted">{s.tool}</span>
          </span>,
          <span className="mono" key="input">
            {JSON.stringify(s.input ?? {})}
          </span>,
          s.is_error ? "Error" : show(s.rows),
          s.ms === undefined ? "No data" : `${s.ms} ms`,
        ])}
      />
      <dl className="kv" style={{ marginTop: 12 }}>
        <dt>Model</dt>
        <dd className="mono">{result.served_by ?? result.model ?? "No data"}</dd>
        <dt>Model calls</dt>
        <dd>{show(usage?.api_calls)}</dd>
        <dt>Input tokens</dt>
        <dd>{show(usage?.input_tokens)}</dd>
        <dt>Output tokens</dt>
        <dd>{show(usage?.output_tokens)}</dd>
        <dt>Cache writes (tokens)</dt>
        <dd>{show(usage?.cache_creation_input_tokens)}</dd>
        <dt>Cache reads (tokens)</dt>
        <dd>{show(usage?.cache_read_input_tokens)}</dd>
        <dt>Cache hits</dt>
        <dd>{show(usage?.cache_hits)}</dd>
        <dt>Latency</dt>
        <dd>{result.latency_ms === undefined ? "No data" : `${result.latency_ms} ms`}</dd>
        <dt>Estimated cost</dt>
        <dd>{result.estimated_cost_usd === undefined ? "No data" : `${result.estimated_cost_usd} USD`}</dd>
        <dt>Data as of</dt>
        <dd>{formatDateTime(result.as_of)}</dd>
      </dl>
    </>
  );
}
