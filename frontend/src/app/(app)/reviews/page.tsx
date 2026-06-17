"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CheckSquare } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { analysisApi, reviewsApi } from "@/lib/api";
import { formatDate, formatRiskScore, riskScoreColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AnalysisJob, Review } from "@/types";

const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

/** Derive the review state shown in the list for a reviewable job. */
function reviewStateFor(job: AnalysisJob, review: Review | undefined): string {
  if (review) return review.status; // in_progress | approved | rejected
  if (job.status === "awaiting_review") return "not_started";
  return job.status; // e.g. completed without a separate review record
}

export default function ReviewsPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<string>("all");

  const jobsQuery = useQuery({
    queryKey: ["jobs", "reviewable"],
    queryFn: () => analysisApi.listJobs(1, 100),
  });
  const reviewsQuery = useQuery({
    queryKey: ["reviews", "list"],
    queryFn: () => reviewsApi.listReviews(1, 100),
  });

  const isLoading = jobsQuery.isLoading || reviewsQuery.isLoading;

  const rows = useMemo(() => {
    const jobs = jobsQuery.data ?? [];
    const reviews = reviewsQuery.data ?? [];
    const byJob = new Map(reviews.map((r) => [r.analysis_job_id, r]));

    return jobs
      // A job is reviewable if analysis finished, was signed off, or already
      // has a review record (e.g. a rejection sent it back to awaiting_review).
      .filter(
        (job) =>
          job.status === "awaiting_review" ||
          job.status === "completed" ||
          byJob.has(job.id),
      )
      .map((job) => ({ job, state: reviewStateFor(job, byJob.get(job.id)) }))
      .filter((row) => filter === "all" || row.state === filter);
  }, [jobsQuery.data, reviewsQuery.data, filter]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Review status" />
          </SelectTrigger>
          <SelectContent>
            {FILTER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-6">
          {isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={CheckSquare}
              title="Nothing to review"
              description="Completed analysis jobs that need human sign-off will appear here."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Risk Score</TableHead>
                  <TableHead>Review Status</TableHead>
                  <TableHead className="text-right">Completed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(({ job, state }) => (
                  <TableRow
                    key={job.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/reviews/${job.id}`)}
                  >
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {job.id.slice(0, 8)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "font-semibold tabular-nums",
                        riskScoreColor(job.overall_risk_score),
                      )}
                    >
                      {formatRiskScore(job.overall_risk_score)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={state} />
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatDate(job.completed_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
