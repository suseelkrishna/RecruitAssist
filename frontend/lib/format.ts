/**
 * Display formatting for values the API returns. These change how a value is written, never
 * the value itself. All times are shown in UTC, the time zone the data uses.
 */

const DATE = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", year: "numeric", month: "short", day: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** A UTC timestamp as a date, for example "Nov 9, 2026". */
export function formatDate(ts: string | null | undefined): string {
  return ts ? DATE.format(new Date(ts)) : "Not set";
}

/** A UTC timestamp as a date and time, for example "Nov 9, 2026, 17:00 UTC". */
export function formatDateTime(ts: string | null | undefined): string {
  return ts ? `${DATE_TIME.format(new Date(ts))} UTC` : "Not set";
}

/** A number as given, or a dash with a label when the API has no value. */
export function show(value: number | null | undefined, suffix = ""): string {
  return value === null || value === undefined ? "No data" : `${value}${suffix}`;
}

/** A stage or status name such as "offer_follow_up" written as words. */
export function words(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
