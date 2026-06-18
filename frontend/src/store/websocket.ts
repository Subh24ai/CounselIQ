import { create } from "zustand";

import { refreshAccessToken } from "@/lib/api";
import { getSharedQueryClient } from "@/lib/queryClient";
import type { AgentStep, JobStatus, WebSocketMessage } from "@/types";

const WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"
).replace(/\/$/, "");

// Exponential backoff schedule: 1s, 2s, 4s, 8s, ... capped at 30s.
const BASE_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

// Refresh the access token before connecting if it has already expired or will
// expire within this window — a stale token is rejected pre-accept (a spurious
// 403 on load), so we proactively refresh just like the HTTP client does.
const TOKEN_REFRESH_THRESHOLD_SEC = 30;

// Server-side close codes (see app/api/v1/websocket.py). These are permanent
// authentication/authorisation rejections — reconnecting cannot help.
const WS_CLOSE_INVALID_TOKEN = 4001;
const WS_CLOSE_WRONG_ORG = 4003;
// Abnormal closure (network drop, or a handshake rejected before accept — the
// browser never sees a server-supplied 4001/4003 in that case, only 1006).
const WS_CLOSE_ABNORMAL = 1006;

interface WSState {
  socket: WebSocket | null;
  isConnected: boolean;
  connectionError: string | null;
  jobUpdates: Record<string, JobStatus>;
  agentSteps: Record<string, AgentStep[]>;

  connect: (organisationId: string, token: string) => void;
  disconnect: () => void;
  clearJobData: (jobId: string) => void;
}

// Module-level connection bookkeeping (kept out of reactive state).
let reconnectAttempts = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
// Set when disconnect() is called so the close handler does not reconnect.
let intentionalClose = false;
let lastOrganisationId: string | null = null;
let lastToken: string | null = null;
// Bumped on every connect()/disconnect() so a slow async open (awaiting a token
// refresh) can detect that it has been superseded and bail out.
let connectionGeneration = 0;

function backoffDelay(attempt: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
}

/** Decode a JWT's ``exp`` (seconds since epoch) without verifying the signature. */
function decodeJwtExp(token: string): number | null {
  try {
    const segment = token.split(".")[1];
    if (!segment) return null;
    const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

/**
 * True when the token is already expired or within
 * ``TOKEN_REFRESH_THRESHOLD_SEC`` of expiring. Opaque/undecodable tokens return
 * false so we fall back to letting the server decide.
 */
function isTokenExpiringSoon(token: string): boolean {
  const exp = decodeJwtExp(token);
  if (exp === null) return false;
  const nowSec = Date.now() / 1000;
  return exp - nowSec <= TOKEN_REFRESH_THRESHOLD_SEC;
}

// Only transient/network closures are worth retrying. A handshake rejected
// before the server accepts it surfaces as 1006 in the browser; a clean
// network drop is also 1006; some browsers report 0/undefined on failure.
function isReconnectable(code: number): boolean {
  return code === WS_CLOSE_ABNORMAL || code === 0;
}

export const useWebSocketStore = create<WSState>((set, get) => ({
  socket: null,
  isConnected: false,
  connectionError: null,
  jobUpdates: {},
  agentSteps: {},

  connect: (organisationId, token) => {
    if (typeof window === "undefined") return;

    lastOrganisationId = organisationId;
    lastToken = token;
    intentionalClose = false;
    // Invalidates any in-flight async open from a previous connect()/disconnect().
    const generation = ++connectionGeneration;

    // Tear down any existing socket before opening a new one.
    const existing = get().socket;
    if (existing) {
      existing.onclose = null;
      existing.onerror = null;
      existing.close();
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    // Opening the socket may need an async token refresh first, so the work
    // runs in a detached task. connect() stays fire-and-forget to match its
    // call sites (the app layout effect).
    void (async () => {
      let activeToken = token;

      // Proactively refresh a stale/expiring token so the handshake is not
      // rejected pre-accept (a spurious 403 on load). Reuses the axios
      // client's single-flight refresh.
      if (isTokenExpiringSoon(token)) {
        try {
          activeToken = await refreshAccessToken();
          lastToken = activeToken;
        } catch {
          set({
            isConnected: false,
            connectionError:
              "Live updates unavailable: your session could not be refreshed. Please sign in again.",
          });
          return;
        }
      }

      // A disconnect() or newer connect() may have superseded us during the
      // await; abandon this now-stale open.
      if (intentionalClose || generation !== connectionGeneration) return;

      const url = `${WS_BASE}/ws/${organisationId}?token=${encodeURIComponent(activeToken)}`;
      const socket = new WebSocket(url);
      // Opening a socket is not the same as being connected: the server may
      // still reject the handshake (403) or close it. isConnected only flips
      // true when the server sends its {"type":"connected"} acknowledgement.
      set({ socket, isConnected: false });

      socket.onopen = () => {
        // TCP/TLS handshake succeeded — but NOT server acceptance. Do not set
        // isConnected here; wait for the "connected" message in onmessage.
      };

      socket.onmessage = (event) => {
        let message: WebSocketMessage;
        try {
          message = JSON.parse(event.data) as WebSocketMessage;
        } catch {
          return;
        }

        switch (message.type) {
          case "connected":
            // The only place isConnected becomes true: the server has
            // authenticated us and confirmed the connection.
            reconnectAttempts = 0;
            set({ isConnected: true, connectionError: null });
            break;
          case "job_update":
            if (message.job_id && message.status) {
              set((state) => ({
                jobUpdates: {
                  ...state.jobUpdates,
                  [message.job_id as string]: message.status as JobStatus,
                },
              }));
              // A status change (running/awaiting_review/completed/failed —
              // including 'failed' published by the maintenance recovery task)
              // must refresh any view of this job, the document's job list, and
              // the document itself, so stale guards (e.g. the Analyse button)
              // can't persist. Keys are broad because the job_update payload
              // carries no document id.
              const qc = getSharedQueryClient();
              void qc?.invalidateQueries({ queryKey: ["job", message.job_id] });
              void qc?.invalidateQueries({ queryKey: ["jobs"] });
              void qc?.invalidateQueries({ queryKey: ["document"] });
            }
            break;
          case "agent_step":
            if (message.job_id && message.step) {
              const jobId = message.job_id;
              const step = message.step;
              set((state) => ({
                agentSteps: {
                  ...state.agentSteps,
                  [jobId]: [...(state.agentSteps[jobId] ?? []), step],
                },
              }));
            }
            break;
          case "review_flag_updated":
            // Another reviewer changed a flag — refresh this job's review and
            // its summary counts so all viewers stay in sync.
            if (message.job_id) {
              const qc = getSharedQueryClient();
              void qc?.invalidateQueries({
                queryKey: ["review", message.job_id],
              });
              void qc?.invalidateQueries({
                queryKey: ["review-summary", message.job_id],
              });
            }
            break;
          case "review_submitted":
            // The review was approved/rejected elsewhere — refresh the review
            // plus the job/report so the analysis view reflects the new status.
            if (message.job_id) {
              const qc = getSharedQueryClient();
              const jobId = message.job_id;
              for (const key of [
                ["review", jobId],
                ["review-summary", jobId],
                ["job", jobId],
                ["report", jobId],
              ]) {
                void qc?.invalidateQueries({ queryKey: key });
              }
            }
            break;
          default:
            break;
        }
      };

      socket.onerror = () => {
        // An error always precedes an abnormal close; record it and let onclose
        // decide whether to reconnect.
        console.error("WebSocket error for org", organisationId);
        set({ isConnected: false });
      };

      socket.onclose = (event) => {
        // A closed socket is never "connected", whatever the reason.
        set({ isConnected: false, socket: null });

        if (intentionalClose) return;

        // Permanent auth/authorisation rejection: do not reconnect. (Delivered
        // only when the socket was accepted then closed by the server; a
        // pre-accept 403 arrives as 1006 and is handled as reconnectable below.)
        if (
          event.code === WS_CLOSE_INVALID_TOKEN ||
          event.code === WS_CLOSE_WRONG_ORG
        ) {
          lastOrganisationId = null;
          lastToken = null;
          reconnectAttempts = 0;
          set({
            connectionError:
              event.code === WS_CLOSE_INVALID_TOKEN
                ? "Live updates unavailable: your session is invalid or expired. Please sign in again."
                : "Live updates unavailable: not authorised for this organisation.",
          });
          return;
        }

        // Anything else that isn't a transient/network closure (e.g. a clean
        // server-side 1000/1001) is left disconnected without retrying.
        if (!isReconnectable(event.code) || !lastOrganisationId || !lastToken) {
          set({ connectionError: "Live updates disconnected." });
          return;
        }

        // Transient/network closure — reconnect with exponential backoff.
        set({ connectionError: "Live updates disconnected — reconnecting…" });
        const delay = backoffDelay(reconnectAttempts);
        reconnectAttempts += 1;
        reconnectTimer = setTimeout(() => {
          get().connect(lastOrganisationId as string, lastToken as string);
        }, delay);
      };
    })();
  },

  disconnect: () => {
    intentionalClose = true;
    lastOrganisationId = null;
    lastToken = null;
    reconnectAttempts = 0;
    // Supersede any in-flight async open awaiting a token refresh.
    connectionGeneration += 1;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const socket = get().socket;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
    set({ socket: null, isConnected: false, connectionError: null });
  },

  clearJobData: (jobId) => {
    set((state) => {
      const jobUpdates = { ...state.jobUpdates };
      const agentSteps = { ...state.agentSteps };
      delete jobUpdates[jobId];
      delete agentSteps[jobId];
      return { jobUpdates, agentSteps };
    });
  },
}));
