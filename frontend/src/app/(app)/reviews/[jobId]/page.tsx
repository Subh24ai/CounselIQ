"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { ArrowLeft, Loader2 } from "lucide-react";

import { RiskFlagCard } from "@/components/analysis/RiskFlagCard";
import { SubmitReviewBar } from "@/components/reviews/SubmitReviewBar";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { RiskScoreGauge } from "@/components/shared/RiskScoreGauge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { analysisApi, reviewsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type {
  AnalysisJob,
  FlagSeverity,
  JobStatus,
  JobType,
  ReviewSummaryResponse,
} from "@/types";

const JOB_TYPE_LABELS: Record<JobType, string> = {
  contract_review: "Contract Review",
  due_diligence: "Due Diligence",
  reg_compliance: "Regulatory Compliance",
  risk_assessment: "Risk Assessment",
};

const SEVERITY_ORDER: FlagSeverity[] = ["critical", "high", "medium", "low"];

function getErrorStatus(error: unknown): number | undefined {
  return isAxiosError(error) ? error.response?.status : undefined;
}

function severityRank(severity: FlagSeverity | null): number {
  if (!severity) return SEVERITY_ORDER.length;
  const idx = SEVERITY_ORDER.indexOf(severity);
  return idx === -1 ? SEVERITY_ORDER.length : idx;
}

function BackLink() {
  return (
    <Link
      href="/reviews"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Reviews
    </Link>
  );
}

export default function ReviewDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const queryClient = useQueryClient();

  const [startError, setStartError] = useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => analysisApi.getJob(jobId),
  });

  // getReview 404s until a review has been started — don't retry, treat the
  // 404 as the "no review yet" state rather than an error.
  const reviewQuery = useQuery({
    queryKey: ["review", jobId],
    queryFn: () => reviewsApi.getReview(jobId),
    retry: false,
  });

  const review = reviewQuery.data;
  const reviewMissing =
    reviewQuery.isError && getErrorStatus(reviewQuery.error) === 404;
  const reviewActive =
    !!review && (review.status === "in_progress" || review.status === "pending");
  const reviewAlreadySubmitted =
    !!review && (review.status === "approved" || review.status === "rejected");

  // The summary endpoint works without a started review (it counts the job's
  // flags), so enable it whenever the job is loaded — it powers both the
  // Start-Review prompt's flag count and the live review counts.
  const summaryQuery = useQuery({
    queryKey: ["review-summary", jobId],
    queryFn: () => reviewsApi.getSummary(jobId),
    enabled: !!jobQuery.data,
  });
  const summary = summaryQuery.data;

  const startMutation = useMutation({
    mutationFn: () => reviewsApi.startReview(jobId),
    onSuccess: async () => {
      setStartError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["job", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["review-summary", jobId] }),
      ]);
    },
    onError: (error) => setStartError(getApiErrorMessage(error)),
  });

  if (jobQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading review…" />
      </div>
    );
  }

  const job = jobQuery.data;
  if (jobQuery.isError || !job) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            This analysis job could not be found.
          </CardContent>
        </Card>
      </div>
    );
  }

  const jobTypeLabel = JOB_TYPE_LABELS[job.job_type] ?? job.job_type;
  const score = job.overall_risk_score ?? 0;

  const sortedFlags = review
    ? [...review.risk_flags].sort(
        (a, b) => severityRank(a.severity) - severityRank(b.severity),
      )
    : [];

  function renderBody(job: AnalysisJob) {
    if (reviewQuery.isLoading) {
      return (
        <div className="flex h-48 items-center justify-center">
          <LoadingSpinner label="Loading review…" />
        </div>
      );
    }

    if (reviewActive && review) {
      return (
        <div className="space-y-6 pb-4">
          <SummaryBar summary={summary} loading={summaryQuery.isLoading} />

          <div className="space-y-3">
            {sortedFlags.length === 0 ? (
              <Card>
                <CardContent className="p-6 text-sm text-muted-foreground">
                  This review has no risk flags to action.
                </CardContent>
              </Card>
            ) : (
              sortedFlags.map((flag) => (
                <RiskFlagCard key={flag.id} flag={flag} jobId={jobId} />
              ))
            )}
          </div>

          <SubmitReviewBar jobId={jobId} summary={summary} />
        </div>
      );
    }

    if (reviewAlreadySubmitted && review) {
      return (
        <Card>
          <CardContent className="space-y-2 p-6">
            <h3 className="font-semibold">Review already {review.status}</h3>
            <p className="text-sm text-muted-foreground">
              This review has already been {review.status} and can no longer be
              edited.
            </p>
            {review.notes && (
              <p className="text-sm">
                <span className="font-medium">Reviewer notes: </span>
                {review.notes}
              </p>
            )}
            <Button asChild variant="outline" size="sm">
              <Link href={`/analysis/${jobId}`}>View analysis report</Link>
            </Button>
          </CardContent>
        </Card>
      );
    }

    if (reviewMissing) {
      if (job.status === "awaiting_review") {
        const flagCount = summary?.total_flags;
        return (
          <Card>
            <CardContent className="space-y-4 p-6">
              <div>
                <h3 className="text-lg font-semibold">Ready for review</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  This analysis is awaiting human sign-off. Start a review to
                  work through the risk flags and approve or reject the
                  findings.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-6">
                <RiskScoreGauge score={score} size={96} />
                <div className="text-sm">
                  <p className="font-medium">
                    {flagCount == null
                      ? "Loading flag count…"
                      : `${flagCount} risk flag${flagCount === 1 ? "" : "s"} to review`}
                  </p>
                  {summary && summary.critical_open > 0 && (
                    <p className="text-destructive">
                      {summary.critical_open} critical
                    </p>
                  )}
                </div>
              </div>

              <Button
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
              >
                {startMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Start Review
              </Button>
            </CardContent>
          </Card>
        );
      }
      return <NotAwaitingReview status={job.status} />;
    }

    // Non-404 failure loading the review.
    if (reviewQuery.isError) {
      return (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            The review for this job could not be loaded. Please try again.
          </CardContent>
        </Card>
      );
    }

    return null;
  }

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h2 className="text-xl font-semibold">{jobTypeLabel}</h2>
          <p className="text-sm text-muted-foreground">
            Job {job.id.slice(0, 8)}
          </p>
          <div className="mt-2">
            <StatusBadge status={job.status} />
          </div>
        </div>
        <RiskScoreGauge score={score} size={120} />
      </div>

      {startError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {startError}
        </div>
      )}

      {renderBody(job)}
    </div>
  );
}

function SummaryBar({
  summary,
  loading,
}: {
  summary: ReviewSummaryResponse | undefined;
  loading: boolean;
}) {
  if (!summary) {
    return (
      <p className="text-sm text-muted-foreground">
        {loading ? "Loading flag counts…" : "Flag counts unavailable."}
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="font-medium">{summary.open} open</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{summary.accepted} accepted</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{summary.rejected} rejected</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{summary.resolved} resolved</span>
      <span className="text-muted-foreground">·</span>
      <span
        className={cn(
          summary.critical_open > 0
            ? "font-semibold text-destructive"
            : "font-medium text-emerald-600",
        )}
      >
        {summary.critical_open} critical open
      </span>
    </div>
  );
}

function NotAwaitingReview({ status }: { status: JobStatus }) {
  const explanation: Record<JobStatus, string> = {
    pending:
      "Analysis hasn't started yet. A review can begin once analysis finishes.",
    running:
      "Analysis is still in progress. A review can begin once it finishes.",
    awaiting_review: "This job is awaiting review.",
    completed: "This job has already been completed and signed off.",
    failed: "This analysis failed, so there is nothing to review.",
  };
  return (
    <Card>
      <CardContent className="space-y-3 p-6">
        <h3 className="font-semibold">This job is not awaiting review</h3>
        <div>
          <StatusBadge status={status} />
        </div>
        <p className="text-sm text-muted-foreground">{explanation[status]}</p>
      </CardContent>
    </Card>
  );
}
