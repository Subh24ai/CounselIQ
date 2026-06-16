"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Brain,
  CheckSquare,
  ClipboardCheck,
  FileText,
  Loader2,
} from "lucide-react";
import { isThisMonth, parseISO } from "date-fns";

import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { analysisApi, documentsApi } from "@/lib/api";
import { formatDate, formatRiskScore, riskScoreColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AnalysisJob, JobType } from "@/types";

const JOB_TYPE_LABELS: Record<JobType, string> = {
  contract_review: "Contract Review",
  due_diligence: "Due Diligence",
  reg_compliance: "Reg. Compliance",
  risk_assessment: "Risk Assessment",
};

function StatCard({
  label,
  value,
  icon: Icon,
  loading,
}: {
  label: string;
  value: number;
  icon: typeof FileText;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-6">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          {loading ? (
            <Skeleton className="mt-1 h-7 w-10" />
          ) : (
            <p className="text-2xl font-bold tabular-nums">{value}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const documentsQuery = useQuery({
    queryKey: ["documents", "dashboard"],
    queryFn: () => documentsApi.listDocuments(1, 5),
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", "dashboard"],
    queryFn: () => analysisApi.listJobs(1, 100),
  });

  const jobs: AnalysisJob[] = jobsQuery.data ?? [];
  const recentJobs = jobs.slice(0, 5);
  const recentDocuments = documentsQuery.data?.items ?? [];

  const activeJobs = jobs.filter(
    (j) => j.status === "pending" || j.status === "running",
  ).length;
  const pendingReviews = jobs.filter(
    (j) => j.status === "awaiting_review",
  ).length;
  const completedThisMonth = jobs.filter(
    (j) =>
      j.status === "completed" &&
      j.completed_at &&
      isThisMonth(parseISO(j.completed_at)),
  ).length;

  const statsLoading = documentsQuery.isLoading || jobsQuery.isLoading;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Documents"
          value={documentsQuery.data?.total ?? 0}
          icon={FileText}
          loading={documentsQuery.isLoading}
        />
        <StatCard
          label="Active Analysis Jobs"
          value={activeJobs}
          icon={Brain}
          loading={jobsQuery.isLoading}
        />
        <StatCard
          label="Pending Reviews"
          value={pendingReviews}
          icon={CheckSquare}
          loading={jobsQuery.isLoading}
        />
        <StatCard
          label="Completed This Month"
          value={completedThisMonth}
          icon={ClipboardCheck}
          loading={jobsQuery.isLoading}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent documents */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent Documents</CardTitle>
            <Link
              href="/documents"
              className="text-sm font-medium text-primary hover:underline"
            >
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {documentsQuery.isLoading ? (
              <TableSkeleton columns={3} />
            ) : recentDocuments.length === 0 ? (
              <EmptyState
                icon={FileText}
                title="No documents yet"
                description="Upload a contract to begin compliance analysis."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Uploaded</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentDocuments.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell className="max-w-48 truncate font-medium">
                        {doc.name}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={doc.status} />
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {formatDate(doc.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Recent analysis jobs */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent Analysis Jobs</CardTitle>
            <Link
              href="/analysis"
              className="text-sm font-medium text-primary hover:underline"
            >
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {jobsQuery.isLoading ? (
              <TableSkeleton columns={3} />
            ) : recentJobs.length === 0 ? (
              <EmptyState
                icon={Brain}
                title="No analysis jobs yet"
                description="Run an analysis on a document to see results here."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentJobs.map((job) => (
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
                      <TableCell className="text-right">
                        <StatusBadge status={job.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Risk score legend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Risk Score Legend</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-6 text-sm">
          <LegendItem color="bg-emerald-500" label="Low" range="0 – 30" />
          <LegendItem color="bg-amber-500" label="Medium" range="31 – 60" />
          <LegendItem color="bg-destructive" label="High" range="61 – 100" />
          {jobsQuery.isError && (
            <span className="flex items-center gap-2 text-destructive">
              <Loader2 className="h-4 w-4" />
              Couldn&apos;t load analysis jobs.
            </span>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function LegendItem({
  color,
  label,
  range,
}: {
  color: string;
  label: string;
  range: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn("h-3 w-3 rounded-full", color)} />
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">{range}</span>
    </div>
  );
}

function TableSkeleton({ columns }: { columns: number }) {
  return (
    <div className="space-y-3">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex gap-4">
          {Array.from({ length: columns }).map((_, col) => (
            <Skeleton key={col} className="h-5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
