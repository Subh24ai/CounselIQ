"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckSquare } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { analysisApi } from "@/lib/api";
import { formatDate, formatRiskScore, riskScoreColor } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function ReviewsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["jobs", "reviewable"],
    queryFn: () => analysisApi.listJobs(1, 100),
  });

  // Reviews act on jobs that have finished analysis.
  const reviewable = (data ?? []).filter(
    (job) => job.status === "awaiting_review" || job.status === "completed",
  );

  return (
    <Card>
      <CardContent className="p-6">
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : reviewable.length === 0 ? (
          <EmptyState
            icon={CheckSquare}
            title="Nothing awaiting review"
            description="Completed analysis jobs that need human sign-off will appear here."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job</TableHead>
                <TableHead>Risk Score</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reviewable.map((job) => (
                <TableRow key={job.id}>
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
                    <StatusBadge status={job.status} />
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
  );
}
