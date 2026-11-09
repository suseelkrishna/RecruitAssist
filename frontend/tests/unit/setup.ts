/**
 * Browser APIs jsdom does not provide but the kit's Radix components and Recharts call.
 * Each stub does nothing; the tests check what the components render and send.
 */

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => undefined;
Element.prototype.scrollIntoView ??= () => undefined;

// next/link needs the app router; a plain anchor is enough for these tests.
vi.mock("next/link", async () => {
  const React = await import("react");
  return {
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
      React.createElement("a", { href, ...rest }, children),
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = "demo_user=; path=/; max-age=0";
});
