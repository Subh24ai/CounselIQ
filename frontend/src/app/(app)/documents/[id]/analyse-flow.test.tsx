import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AnalysisJob, Document } from "@/types";

const DOC_ID = "11111111-1111-1111-1111-111111111111";
const EXISTING_JOB_ID = "df23364d-d191-4406-a5af-2e18751cb5cc";
const NEW_JOB_ID = "99999999-9999-9999-9999-999999999999";

const getDocumentMock = vi.fn();
const listJobsMock = vi.fn();
const createJobMock = vi.fn();
const pushMock = vi.fn();

vi.mock("@/lib/api", () => ({
  documentsApi: { getDocument: (...a: unknown[]) => getDocumentMock(...a) },
  analysisApi: {
    listJobs: (...a: unknown[]) => listJobsMock(...a),
    createJob: (...a: unknown[]) => createJobMock(...a),
  },
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: DOC_ID }),
  useRouter: () => ({ push: pushMock }),
}));

import DocumentDetailPage from "./page";

function completedDocument(): Document {
  return {
    id: DOC_ID,
    name: "test-nda",
    original_filename: "test-nda.pdf",
    document_type: "nda",
    status: "completed", // already analysed
    file_size_bytes: 1024,
    page_count: 3,
    mime_type: "application/pdf",
    uploaded_by: "user-1",
    created_at: new Date().toISOString(),
    presigned_url: null,
  };
}

const FAILED_JOB_ID = "96bfddf4-070e-4a10-93a3-a670783ab59b";

function completedJob(): AnalysisJob {
  return {
    id: EXISTING_JOB_ID,
    document_id: DOC_ID,
    status: "completed",
    job_type: "contract_review",
    overall_risk_score: 71.8,
    agent_trace: [],
    error_message: null,
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
  };
}

// Exactly the live bug shape: the document is orphaned in 'analysing' and its
// second job was recovered to 'failed' — yet NO job is pending/running.
function analysingOrphanedDocument(): Document {
  return { ...completedDocument(), status: "analysing" };
}

function failedJob(): AnalysisJob {
  return {
    ...completedJob(),
    id: FAILED_JOB_ID,
    status: "failed",
    overall_risk_score: null,
    completed_at: new Date().toISOString(),
    error_message: "Job exceeded maximum runtime and was marked failed.",
  };
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DocumentDetailPage />
    </QueryClientProvider>,
  );
}

describe("Document detail — re-analyse an already-analysed document", () => {
  it("creates a new job for a completed document with existing history", async () => {
    getDocumentMock.mockReset().mockResolvedValue(completedDocument());
    listJobsMock.mockReset().mockResolvedValue([completedJob()]);
    createJobMock
      .mockReset()
      .mockResolvedValue({ ...completedJob(), id: NEW_JOB_ID, status: "pending" });

    renderPage();

    // The Analyse button must be available and enabled for a completed doc.
    const analyseBtn = await screen.findByRole("button", { name: /analyse/i });
    expect((analyseBtn as HTMLButtonElement).disabled).toBe(false);

    // Open the dialog.
    fireEvent.click(analyseBtn);
    const startBtn = await screen.findByRole("button", {
      name: /start analysis/i,
    });

    // Default job type is Contract Review; submit.
    fireEvent.click(startBtn);

    await waitFor(() => expect(createJobMock).toHaveBeenCalledTimes(1));
    expect(createJobMock).toHaveBeenCalledWith({
      document_id: DOC_ID,
      job_type: "contract_review",
    });

    // And it routes to the NEW job, not the existing one.
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(`/analysis/${NEW_JOB_ID}`),
    );
    expect(NEW_JOB_ID).not.toBe(EXISTING_JOB_ID);
  });

  it("enables Analyse for a document orphaned in 'analysing' with one completed + one failed job", async () => {
    // The exact live regression: doc stuck 'analysing', jobs = completed + failed,
    // zero in-progress. The button must be ENABLED and clicking it must POST.
    getDocumentMock.mockReset().mockResolvedValue(analysingOrphanedDocument());
    listJobsMock.mockReset().mockResolvedValue([completedJob(), failedJob()]);
    createJobMock
      .mockReset()
      .mockResolvedValue({ ...completedJob(), id: NEW_JOB_ID, status: "pending" });

    renderPage();

    const analyseBtn = await screen.findByRole("button", { name: /analyse/i });
    expect((analyseBtn as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(analyseBtn);
    const startBtn = await screen.findByRole("button", {
      name: /start analysis/i,
    });
    fireEvent.click(startBtn);

    await waitFor(() => expect(createJobMock).toHaveBeenCalledTimes(1));
    expect(createJobMock).toHaveBeenCalledWith({
      document_id: DOC_ID,
      job_type: "contract_review",
    });
  });
});
