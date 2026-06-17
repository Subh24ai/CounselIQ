"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { RiskScoreGauge } from "@/components/shared/RiskScoreGauge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
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
import { analysisApi, documentsApi } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { JobStatus, JobType } from "@/types";

const POLL_STATUSES: JobStatus[] = ["pending", "running"];

const STATUS_OPTIONS: JobStatus[] = [
  "pending",
  "running",
  "awaiting_review",
  "completed",
  "failed",
];

const JOB_TYPE_LABELS: Record<JobType, string> = {
  contract_review: "Contract Review",
  due_diligence: "Due Diligence",
  reg_compliance: "Reg. Compliance",
  risk_assessment: "Risk Assessment",
};

function humanize(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function AnalysisPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const jobsQuery = useQuery({
    queryKey: ["jobs", "list"],
    queryFn: () => analysisApi.listJobs(1, 100),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some((j) => POLL_STATUSES.includes(j.status)) ? 4000 : false;
    },
  });

  // Resolve document names for display (the job payload only carries the id).
  const documentsQuery = useQuery({
    queryKey: ["documents", "name-map"],
    queryFn: () => documentsApi.listDocuments(1, 100),
  });

  const docNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const doc of documentsQuery.data?.items ?? []) {
      map.set(doc.id, doc.name);
    }
    return map;
  }, [documentsQuery.data]);

  const jobs = jobsQuery.data ?? [];
  const filtered =
    statusFilter === "all"
      ? jobs
      : jobs.filter((j) => j.status === statusFilter);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Analysis Jobs</h2>
          <p className="text-sm text-muted-foreground">
            Multi-agent compliance reviews of your documents.
          </p>
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {jobsQuery.isLoading ? (
            <div className="space-y-3 p-6">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : jobsQuery.isError ? (
            <div className="p-6 text-sm text-destructive">
              Couldn&apos;t load analysis jobs. Please retry.
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={Brain}
                title={
                  jobs.length === 0
                    ? "No analysis jobs yet"
                    : "No matching jobs"
                }
                description={
                  jobs.length === 0
                    ? "Start an analysis from a completed document to see results here."
                    : "Try a different status filter."
                }
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="max-w-56 truncate font-medium">
                      <Link
                        href={`/analysis/${job.id}`}
                        className="hover:underline"
                      >
                        {docNames.get(job.document_id) ??
                          `${job.document_id.slice(0, 8)}…`}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
                    </TableCell>
                    <TableCell>
                      {job.overall_risk_score != null ? (
                        <RiskScoreGauge
                          score={job.overall_risk_score}
                          size={44}
                          compact
                        />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={job.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(job.started_at ?? job.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link href={`/analysis/${job.id}`}>View Report</Link>
                      </Button>
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
