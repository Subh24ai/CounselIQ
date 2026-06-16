"use client";

import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";

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
import type { JobType } from "@/types";

const JOB_TYPE_LABELS: Record<JobType, string> = {
  contract_review: "Contract Review",
  due_diligence: "Due Diligence",
  reg_compliance: "Reg. Compliance",
  risk_assessment: "Risk Assessment",
};

export default function AnalysisPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["jobs", "list"],
    queryFn: () => analysisApi.listJobs(1, 50),
  });

  const jobs = data ?? [];

  return (
    <Card>
      <CardContent className="p-6">
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <EmptyState
            icon={Brain}
            title="No analysis jobs yet"
            description="Analysis jobs run the multi-agent compliance pipeline over your documents."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Risk Score</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="font-medium">
                    {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
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
                    {formatDate(job.created_at)}
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
