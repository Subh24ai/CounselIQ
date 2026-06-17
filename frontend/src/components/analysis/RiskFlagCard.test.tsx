import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const updateFlagMock = vi.fn();
vi.mock("@/lib/api", () => ({
  reviewsApi: {
    updateFlag: (...args: unknown[]) => updateFlagMock(...args),
  },
}));

import { RiskFlagCard } from "./RiskFlagCard";
import { useUIStore } from "@/store/ui";
import type { Review, RiskFlag } from "@/types";

function makeFlag(overrides: Partial<RiskFlag> = {}): RiskFlag {
  return {
    id: "flag-1",
    category: "indemnity",
    severity: "high",
    title: "No liability cap",
    description: null,
    suggested_action: null,
    agent_reasoning: null,
    cited_regulation: null,
    confidence_score: null,
    status: "open",
    notes: null,
    ...overrides,
  };
}

function makeReview(flags: RiskFlag[]): Review {
  return {
    id: "rev-1",
    analysis_job_id: "job-1",
    reviewed_by: null,
    status: "in_progress",
    notes: null,
    approved_at: null,
    created_at: new Date().toISOString(),
    risk_flags: flags,
  };
}

function newClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderCard(flag: RiskFlag, qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <RiskFlagCard flag={flag} jobId="job-1" />
    </QueryClientProvider>,
  );
}

describe("RiskFlagCard review actions", () => {
  it("calls updateFlag with status 'accepted' when Accept is clicked", async () => {
    updateFlagMock.mockReset();
    updateFlagMock.mockResolvedValue({ ...makeFlag(), status: "accepted" });
    const qc = newClient();

    renderCard(makeFlag(), qc);
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));

    await waitFor(() => expect(updateFlagMock).toHaveBeenCalledTimes(1));
    expect(updateFlagMock).toHaveBeenCalledWith("flag-1", {
      status: "accepted",
      notes: null,
    });
  });

  it("rolls back the optimistic update and notifies on error", async () => {
    updateFlagMock.mockReset();
    updateFlagMock.mockRejectedValue(new Error("Network down"));
    useUIStore.setState({ notifications: [] });

    const qc = newClient();
    // Seed the cache the optimistic update mutates.
    qc.setQueryData(["review", "job-1"], makeReview([makeFlag()]));

    renderCard(makeFlag(), qc);
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));

    // The optimistic update is applied then, on failure, rolled back to the
    // exact previous 'open' state — never left showing 'accepted'.
    await waitFor(() => expect(updateFlagMock).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      const cached = qc.getQueryData<Review>(["review", "job-1"]);
      expect(cached?.risk_flags[0].status).toBe("open");
    });

    // …and an error notification is surfaced.
    await waitFor(() => {
      const notes = useUIStore.getState().notifications;
      expect(notes.some((n) => n.type === "error")).toBe(true);
    });
  });
});
