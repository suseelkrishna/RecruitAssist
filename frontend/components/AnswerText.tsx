"use client";

/**
 * Render an answer written in a small subset of Markdown: paragraphs, headings, bullet and
 * numbered lists, tables, and **bold**. Bracketed record IDs such as [APP-014] or
 * [SC-045, SC-060] become citation chips. The text is rendered as React elements, never as HTML, so nothing in it can run.
 */

import { Fragment, type ReactNode } from "react";
import { CitationChip } from "@/components/CitationChip";

const ID = "[A-Z]{2,5}-\\d+";
const INLINE = new RegExp(`(\\*\\*[^*]+\\*\\*|\\[${ID}(?:,\\s*${ID})*\\])`, "g");
const CITATION = new RegExp(`^\\[(${ID}(?:,\\s*${ID})*)\\]$`);

/** One line of text with bold runs and citation chips. */
function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{inline(part.slice(2, -2))}</strong>;
    const cite = part.match(CITATION);
    if (cite)
      return (
        <Fragment key={i}>
          {cite[1].split(/,\s*/).map((id) => (
            <CitationChip key={id} id={id} />
          ))}
        </Fragment>
      );
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** The cells of a Markdown table row such as "| a | b |". */
function cells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "h"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "table"; rows: string[][] };

/** Group the answer's lines into blocks. */
function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = out[out.length - 1];
    if (!line.trim()) {
      out.push({ kind: "p", lines: [] });
      continue;
    }
    if (line.trim().startsWith("|")) {
      if (/^\|?\s*:?-{2,}/.test(line.trim())) continue;
      if (last?.kind === "table") last.rows.push(cells(line));
      else out.push({ kind: "table", rows: [cells(line)] });
      continue;
    }
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) {
      out.push({ kind: "h", text: heading[1] });
      continue;
    }
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (last?.kind === "ul") last.items.push(bullet[1]);
      else out.push({ kind: "ul", items: [bullet[1]] });
      continue;
    }
    const numbered = line.match(/^\s*\d+\.\s+(.*)$/);
    if (numbered) {
      if (last?.kind === "ol") last.items.push(numbered[1]);
      else out.push({ kind: "ol", items: [numbered[1]] });
      continue;
    }
    if (last?.kind === "p") last.lines.push(line);
    else out.push({ kind: "p", lines: [line] });
  }
  return out.filter((b) => b.kind !== "p" || b.lines.length > 0);
}

export function AnswerText({ text }: { text: string }) {
  return (
    <div className="answer">
      {blocks(text).map((b, i) => {
        if (b.kind === "h") return <h3 key={i}>{inline(b.text)}</h3>;
        if (b.kind === "ul")
          return (
            <ul key={i}>
              {b.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ul>
          );
        if (b.kind === "ol")
          return (
            <ol key={i}>
              {b.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ol>
          );
        if (b.kind === "table") {
          const [head, ...body] = b.rows;
          return (
            <div className="answer-table" key={i} tabIndex={0} role="region" aria-label="Answer table">
              <table>
                <thead>
                  <tr>
                    {head.map((c, j) => (
                      <th key={j} scope="col">
                        {inline(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, j) => (
                    <tr key={j}>
                      {row.map((c, k) => (
                        <td key={k}>{inline(c)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={i}>
            {b.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(line)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
