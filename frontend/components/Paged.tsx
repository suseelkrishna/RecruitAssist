"use client";

/**
 * Pagination for long lists and tables. usePaged keeps the current page for a list and goes
 * back to page 1 when the list changes (a new filter or sort), and PageControls shows
 * "Showing 1 to 10 of 42" with the brand kit's Previous and Next buttons. Paging only
 * decides which rows are on screen; every number in a row still comes from the API.
 */

import { Pagination } from "@suseelkrishna/fieryfusion-react";
import { useState } from "react";

export type Paged<T> = {
  /** The rows on the current page. */
  rows: T[];
  page: number;
  pages: number;
  /** Position of the first and last row on this page, counting from 1, and the total. */
  first: number;
  last: number;
  total: number;
  setPage: (page: number) => void;
};

/**
 * The current page of `items`, `size` rows at a time. `resetKey` names the list's filters
 * or sort; when it changes the list starts again at page 1. A page past the end (after rows
 * were removed) shows the last page instead.
 */
export function usePaged<T>(items: T[], size: number, resetKey = ""): Paged<T> {
  const [state, setState] = useState({ key: resetKey, page: 1 });
  const pages = Math.max(1, Math.ceil(items.length / size));
  const wanted = state.key === resetKey ? state.page : 1;
  const page = Math.min(Math.max(1, wanted), pages);
  const start = (page - 1) * size;
  const rows = items.slice(start, start + size);
  return {
    rows,
    page,
    pages,
    first: items.length === 0 ? 0 : start + 1,
    last: start + rows.length,
    total: items.length,
    setPage: (next) => setState({ key: resetKey, page: next }),
  };
}

/** The "Showing" line and the page buttons, or nothing when everything fits on one page. */
export function PageControls<T>({ paged, noun, label }: { paged: Paged<T>; noun: string; label: string }) {
  if (paged.pages <= 1) return null;
  return (
    <div className="page-controls" role="group" aria-label={label}>
      <span className="page-controls-count" aria-live="polite">
        Showing {paged.first} to {paged.last} of {paged.total} {noun}
      </span>
      <Pagination page={paged.page} pages={paged.pages} onChange={paged.setPage} />
    </div>
  );
}
