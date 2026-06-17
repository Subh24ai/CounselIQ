import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount React trees between tests so the DOM and stores don't leak.
afterEach(() => {
  cleanup();
});

// jsdom lacks a few APIs that Radix UI primitives touch. Provide no-op shims.
// Cast through a record so TS doesn't object to (re)assigning lib.dom members.
if (typeof window !== "undefined") {
  const win = window as unknown as Record<string, unknown>;
  const proto = Element.prototype as unknown as Record<string, unknown>;

  if (!win.matchMedia) {
    win.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!win.ResizeObserver) {
    win.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  if (!proto.scrollIntoView) proto.scrollIntoView = vi.fn();
  if (!proto.hasPointerCapture) proto.hasPointerCapture = vi.fn(() => false);
  if (!proto.releasePointerCapture) proto.releasePointerCapture = vi.fn();
}
