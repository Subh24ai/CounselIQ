import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the API module so the store's refresh hook is observable and never makes
// a real network call. vi.hoisted lets the mock factory reference the spy.
const hoisted = vi.hoisted(() => ({ refreshMock: vi.fn() }));
vi.mock("@/lib/api", () => ({
  refreshAccessToken: hoisted.refreshMock,
}));

import { useWebSocketStore } from "./websocket";

// Records the order of side effects so we can prove refresh precedes connect.
let events: string[] = [];

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev?: unknown) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    events.push("ws");
    FakeWebSocket.instances.push(this);
  }

  close(): void {}
}

function makeJwt(expEpochSec: number): string {
  const enc = (obj: object) => btoa(JSON.stringify(obj));
  const header = enc({ alg: "HS256", typ: "JWT" });
  const payload = enc({ sub: "user-1", org: "org-1", exp: expEpochSec });
  return `${header}.${payload}.signature`;
}

const nowSec = () => Math.floor(Date.now() / 1000);

describe("websocket store connect()", () => {
  beforeEach(() => {
    events = [];
    FakeWebSocket.instances = [];
    hoisted.refreshMock.mockReset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    useWebSocketStore.getState().disconnect();
    vi.unstubAllGlobals();
  });

  it("refreshes an expired token before opening the WebSocket", async () => {
    const expiredToken = makeJwt(nowSec() - 60); // expired a minute ago
    const freshToken = makeJwt(nowSec() + 3600); // valid for an hour

    hoisted.refreshMock.mockImplementation(async () => {
      events.push("refresh");
      return freshToken;
    });

    useWebSocketStore.getState().connect("org-1", expiredToken);

    // connect() is fire-and-forget; wait for the async open to reach the socket.
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));

    // Refresh was invoked, and strictly before the WebSocket was constructed.
    expect(hoisted.refreshMock).toHaveBeenCalledTimes(1);
    expect(events).toEqual(["refresh", "ws"]);

    // The socket was opened with the fresh token, never the expired one.
    const opened = FakeWebSocket.instances[0];
    expect(opened.url).toContain(encodeURIComponent(freshToken));
    expect(opened.url).not.toContain(encodeURIComponent(expiredToken));
  });
});
