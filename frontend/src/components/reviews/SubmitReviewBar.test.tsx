import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const submitMock = vi.fn();
vi.mock("@/lib/api", () => ({
  reviewsApi: {
    submitReview: (...args: unknown[]) => submitMock(...args),
  },
}));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

import { SubmitReviewBar } from "./SubmitReviewBar";
import type { ReviewSummaryResponse } from "@/types";

function summary(
  overrides: Partial<ReviewSummaryResponse> = {},
): ReviewSummaryResponse {
  return {
    total_flags: 4,
    accepted: 1,
    rejected: 0,
    resolved: 1,
    open: 2,
    critical_open: 0,
    ...overrides,
  };
}

function renderBar(s: ReviewSummaryResponse | undefined) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <SubmitReviewBar jobId="job-1" summary={s} />
    </QueryClientProvider>,
  );
}

function button(name: RegExp): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

describe("SubmitReviewBar", () => {
  it("disables Approve when critical flags are still open", () => {
    renderBar(summary({ critical_open: 2 }));
    expect(button(/approve review/i).disabled).toBe(true);
  });

  it("enables Approve when no critical flags are open", () => {
    renderBar(summary({ critical_open: 0 }));
    expect(button(/approve review/i).disabled).toBe(false);
  });

  it("requires notes before a rejection can be confirmed", () => {
    renderBar(summary({ critical_open: 0 }));

    // Open the reject dialog.
    fireEvent.click(button(/reject review/i));

    const confirm = button(/confirm rejection/i);
    expect(confirm.disabled).toBe(true); // empty notes block submission

    fireEvent.change(screen.getByLabelText(/rejection reason/i), {
      target: { value: "Liability cap is unacceptable." },
    });

    expect(button(/confirm rejection/i).disabled).toBe(false);
    expect(submitMock).not.toHaveBeenCalled();
  });
});
