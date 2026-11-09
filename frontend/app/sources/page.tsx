"use client";

/**
 * Where the data comes from. Integrations (from GET /api/sources) are the systems the data
 * syncs through; their values are generated, so each card says Simulated. Candidate sources are
 * real counts from the database. The Live strip (from GET /api/health) checks the database,
 * the model API, and the store right now. Admin sees full integration detail, an HR Manager a
 * read-only summary, and an HR User gets the not-found page because the API answers 404.
 */

import { Badge, Card, DataTable, Stack, StatusPill, type StatusTone } from "@suseelkrishna/fieryfusion-react";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Empty, ErrorState, LoadingSkeleton } from "@/components/PageStates";
import { getHealth, getSources } from "@/lib/api";
import { formatDateTime, show } from "@/lib/format";
import type { Integration, LiveCheck } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

const INTEGRATION_TONE: Record<Integration["status"], StatusTone> = { Healthy: "success", Degraded: "warning", Down: "danger" };

const CHECK_LABEL: Record<LiveCheck["status"], [StatusTone, string]> = {
  ok: ["success", "Reachable"],
  not_configured: ["info", "Not configured"],
  error: ["danger", "Not reachable"],
};

/** The "Live" strip: one status per live dependency, with its detail. */
function LiveChecks() {
  const health = useLoad(getHealth, "health");
  return (
    <Card title="Live checks" description="Checked when this page loads. The model API result is cached for 10 minutes.">
      <Badge tone="success">Live</Badge>
      {health.state === "loading" && <p role="status">Checking</p>}
      {(health.state === "error" || health.state === "not_found") && <p>The live checks could not be loaded.</p>}
      {health.state === "ready" && (
        <ul className="grid grid-3 list-plain" style={{ marginTop: 12 }}>
          {health.data.checks.map((c) => {
            const [tone, label] = CHECK_LABEL[c.status] ?? ["warning", c.status];
            const detail =
              c.name === "Database"
                ? `Read-only. Data version ${String(c.generator_version ?? "unknown")}, as of ${formatDateTime(String(c.as_of ?? ""))}.`
                : c.name === "Model API"
                  ? String(c.note ?? c.model ?? "")
                  : String(c.note ?? c.backend ?? "");
            return (
              <li key={c.name}>
                <strong>{c.name}</strong>
                <div>
                  <StatusPill tone={tone}>{label}</StatusPill>
                </div>
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  {detail}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** One integration card. The summary view shows only status, last sync, and mode. */
function IntegrationCard({ row, full }: { row: Integration; full: boolean }) {
  return (
    <Card>
      <div className="card-head">
        <h2>{row.integration}</h2>
        <Badge tone="warning">Simulated</Badge>
      </div>
      <StatusPill tone={INTEGRATION_TONE[row.status]}>{row.status}</StatusPill>
      <dl className="kv" style={{ marginTop: 12 }}>
        <dt>Last sync</dt>
        <dd>{formatDateTime(row.last_sync)}</dd>
        <dt>Sync mode</dt>
        <dd>{row.mode.replace(/_/g, " ")}</dd>
        {full && (
          <>
            <dt>Records synced</dt>
            <dd>{show(row.records)}</dd>
            <dt>Error rate, 24 hours</dt>
            <dd>{show(row.error_rate_24h_pct, "%")}</dd>
            <dt>Last error</dt>
            <dd>{row.last_error ? `${row.last_error.message.untrusted_text} (${formatDateTime(row.last_error.at)})` : "None"}</dd>
          </>
        )}
      </dl>
      {full && row.reasons && row.reasons.length > 0 && <p className="muted">{row.reasons.join(" ")}</p>}
    </Card>
  );
}

export default function SourcesPage() {
  const result = useLoad(getSources, "sources");
  if (result.state === "not_found") notFound();
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <h1>Sources</h1>
          <p>The systems the data syncs through, and where applicants come from.</p>
        </div>
      </div>
      {result.state === "loading" && <LoadingSkeleton blocks={4} label="Loading sources" />}
      {result.state === "error" && <ErrorState message={result.message} onRetry={result.reload} />}
      {result.state === "ready" && (
        <Stack gap={24} className="fade-in">
          <LiveChecks />
          <section aria-labelledby="integrations">
            <h2 id="integrations">Integrations</h2>
            <p className="muted">
              {result.data.integrations_view === "full"
                ? "These values are generated, not synced from real systems, so each card is marked Simulated."
                : "A read-only summary. These values are generated, not synced from real systems, so each card is marked Simulated."}
            </p>
            {result.data.integrations.length === 0 ? (
              <Empty title="No integrations" description="No integration has synced yet." />
            ) : (
              <div className="grid grid-2">
                {result.data.integrations.map((row) => (
                  <IntegrationCard key={row.integration} row={row} full={result.data.integrations_view === "full"} />
                ))}
              </div>
            )}
          </section>
          <section aria-labelledby="candidate-sources">
            <h2 id="candidate-sources">Candidate sources</h2>
            <p className="muted">{result.data.source_quality.takeaway} These are real counts from the database.</p>
            {result.data.source_quality.sources.length === 0 ? (
              <Empty title="No applicants yet" description="No applications in your scope have a source." />
            ) : (
              <DataTable
                caption="Candidate sources in your scope"
                columns={["Source", "Applicants", "Share reaching Onsite", "Hires", "Median days to hire"]}
                rows={result.data.source_quality.sources.map((s) => [
                  s.source,
                  s.applicants,
                  show(s.onsite_rate_pct, "%"),
                  s.hires,
                  show(s.median_days_to_hire),
                ])}
              />
            )}
          </section>
        </Stack>
      )}
    </AppShell>
  );
}
