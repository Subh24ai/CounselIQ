import { create } from "zustand";

import type { AgentStep, JobStatus, WebSocketMessage } from "@/types";

const WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"
).replace(/\/$/, "");

// Exponential backoff schedule: 1s, 2s, 4s, 8s, ... capped at 30s.
const BASE_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

interface WSState {
  socket: WebSocket | null;
  isConnected: boolean;
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

function backoffDelay(attempt: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
}

export const useWebSocketStore = create<WSState>((set, get) => ({
  socket: null,
  isConnected: false,
  jobUpdates: {},
  agentSteps: {},

  connect: (organisationId, token) => {
    if (typeof window === "undefined") return;

    lastOrganisationId = organisationId;
    lastToken = token;
    intentionalClose = false;

    // Tear down any existing socket before opening a new one.
    const existing = get().socket;
    if (existing) {
      existing.onclose = null;
      existing.close();
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    const url = `${WS_BASE}/ws/${organisationId}?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);
    set({ socket });

    socket.onopen = () => {
      reconnectAttempts = 0;
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
          set({ isConnected: true });
          break;
        case "job_update":
          if (message.job_id && message.status) {
            set((state) => ({
              jobUpdates: {
                ...state.jobUpdates,
                [message.job_id as string]: message.status as JobStatus,
              },
            }));
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
        default:
          break;
      }
    };

    socket.onclose = () => {
      set({ isConnected: false, socket: null });
      if (intentionalClose || !lastOrganisationId || !lastToken) return;
      // Reconnect with exponential backoff.
      const delay = backoffDelay(reconnectAttempts);
      reconnectAttempts += 1;
      reconnectTimer = setTimeout(() => {
        get().connect(lastOrganisationId as string, lastToken as string);
      }, delay);
    };

    socket.onerror = () => {
      // Allow the close handler to drive reconnection.
      socket.close();
    };
  },

  disconnect: () => {
    intentionalClose = true;
    lastOrganisationId = null;
    lastToken = null;
    reconnectAttempts = 0;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const socket = get().socket;
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    set({ socket: null, isConnected: false });
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
