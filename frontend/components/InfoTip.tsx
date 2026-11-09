"use client";

/**
 * A small (i) button that explains something in a short card. It is the brand kit's
 * HoverInfoCard, so it opens on hover, keyboard focus, click, or tap, and closes with Escape
 * or a press outside. The button's name is "About <title>" for screen readers; CSS shows it
 * as an (i) icon.
 *
 * On touch screens a tap does not focus the button, and the kit closes the card shortly after
 * the finger lifts unless the button has focus. So a touch press gives the button focus first.
 */

import { HoverInfoCard } from "@suseelkrishna/fieryfusion-react";
import type { PointerEvent, ReactNode } from "react";

/** Focus the (i) button when a finger presses it, so the card stays open after the tap. */
function focusOnTouch(event: PointerEvent<HTMLSpanElement>) {
  if (event.pointerType !== "touch") return;
  const button = (event.target as HTMLElement).closest("button");
  button?.focus({ preventScroll: true });
}

export function InfoTip({ title, children }: { title: string; children: ReactNode }) {
  return (
    <span className="info-tip" onPointerDown={focusOnTouch}>
      <HoverInfoCard label={`About ${title}`} title={title}>
        {children}
      </HoverInfoCard>
    </span>
  );
}
