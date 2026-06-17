import type { QueryClient } from "@tanstack/react-query";

// The app's QueryClient is created per-instance inside <Providers> (so it is
// never shared across requests on the server). Non-React code that needs to
// invalidate queries — notably the WebSocket store reacting to server events —
// reads the registered instance here. It is only ever set in the browser.
let sharedQueryClient: QueryClient | null = null;

export function setSharedQueryClient(client: QueryClient): void {
  sharedQueryClient = client;
}

export function getSharedQueryClient(): QueryClient | null {
  return sharedQueryClient;
}
