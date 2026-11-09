"use client";

/**
 * The question box pinned under the conversation. Enter sends and Shift+Enter starts a new
 * line. While an answer is on its way, Stop cancels it. Focus returns to the box after sending.
 */

import { Button, Textarea } from "@suseelkrishna/fieryfusion-react";
import { useId, useRef, type FormEvent, type KeyboardEvent } from "react";

export function ChatInput({ value, onChange, onSend, onStop, waiting }: {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  onStop: () => void;
  waiting: boolean;
}) {
  const box = useRef<HTMLTextAreaElement>(null);
  const id = useId();

  /** Send the question if there is one and no answer is pending, then put focus back in the box. */
  function send() {
    if (!value.trim() || waiting) return;
    onSend(value);
    box.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    send();
  }

  return (
    // The label, box, and hint use the kit's field classes, laid out by hand so the Send button
    // can sit beside the box on every screen width with the hint underneath both.
    <form className="chat-input ff-field" onSubmit={onSubmit}>
      <label htmlFor={id} className="chat-input-label">
        Your question
      </label>
      <Textarea
        ref={box}
        id={id}
        aria-describedby={`${id}-hint`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        maxLength={1000}
      />
      <div className="chat-input-actions">
        {waiting ? (
          <Button type="button" variant="secondary" onClick={onStop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!value.trim()}>
            Send
          </Button>
        )}
      </div>
      <span id={`${id}-hint`} className="ff-hint chat-input-hint">
        Enter to send, Shift+Enter for a new line.
      </span>
    </form>
  );
}
