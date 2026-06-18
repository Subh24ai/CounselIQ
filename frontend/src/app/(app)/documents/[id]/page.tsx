"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Brain,
  ChevronDown,
  ExternalLink,
  FileText,
} from "lucide-react";

import { AnalyseDialog } from "@/components/documents/AnalyseDialog";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { canStartAnalysis, hasActiveAnalysisJob } from "@/lib/analysis";
import { analysisApi, documentsApi } from "@/lib/api";
import { formatDate, formatRiskScore, riskScoreColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentStatus, JobType } from "@/types";

const POLL_STATUSES: DocumentStatus[] = ["queued", "extracting", "analysing"];

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

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [analyseOpen, setAnalyseOpen] = useState(false);
  const [showText, setShowText] = useState(false);

  const documentQuery = useQuery({
    queryKey: ["document", id],
    queryFn: () => documentsApi.getDocument(id),
    refetchInterval: (query) =>
      query.state.data && POLL_STATUSES.includes(query.state.data.status)
        ? 3000
        : false,
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", "for-document", id],
    queryFn: () => analysisApi.listJobs(1, 100),
    select: (jobs) => jobs.filter((j) => j.document_id === id),
  });

  const doc = documentQuery.data;

  if (documentQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading document…" />
      </div>
    );
  }

  if (documentQuery.isError || !doc) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            This document could not be found or you don&apos;t have access to it.
          </CardContent>
        </Card>
      </div>
    );
  }

  const jobs = jobsQuery.data ?? [];

  // "In progress" is determined SOLELY by live job state — only an actual
  // pending/running job blocks a new analysis. A document orphaned in
  // 'analysing' (a crashed worker that never reset it) must NOT block, because
  // there is no active job.
  const analysisInProgress = hasActiveAnalysisJob(jobs);
  // Re-analysable once extracted; a prior job proves extraction succeeded, so a
  // stale 'analysing'/'failed' document status never blocks re-analysis.
  const canAnalyse = canStartAnalysis(doc.status, jobs);
  const showAnalyse = canAnalyse || analysisInProgress;

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-semibold">{doc.name}</h2>
            <div className="mt-1 flex items-center gap-2">
              <StatusBadge status={doc.status} />
              <span className="text-sm text-muted-foreground">
                {humanize(doc.document_type)}
              </span>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          {doc.presigned_url && (
            <Button variant="outline" asChild>
              <a href={doc.presigned_url} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" />
                View Original
              </a>
            </Button>
          )}
          {showAnalyse &&
            (analysisInProgress ? (
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0}>
                      <Button disabled>
                        <Brain className="mr-2 h-4 w-4" />
                        Analyse
                      </Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    An analysis is already in progress for this document.
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : (
              <Button onClick={() => setAnalyseOpen(true)}>
                <Brain className="mr-2 h-4 w-4" />
                Analyse
              </Button>
            ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Details</CardTitle>
          </CardHeader>
          <CardContent className="divide-y pt-0">
            <MetaRow label="Original file" value={doc.original_filename ?? "—"} />
            <MetaRow label="Type" value={humanize(doc.document_type)} />
            <MetaRow label="Status" value={<StatusBadge status={doc.status} />} />
            <MetaRow label="Pages" value={doc.page_count ?? "—"} />
            <MetaRow label="Size" value={formatBytes(doc.file_size_bytes)} />
            <MetaRow label="MIME type" value={doc.mime_type ?? "—"} />
            <MetaRow label="Uploaded" value={formatDate(doc.created_at)} />
          </CardContent>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          {/* Analysis history */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Analysis History</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {jobsQuery.isLoading ? (
                <LoadingSpinner size="sm" />
              ) : jobs.length === 0 ? (
                <p className="py-4 text-sm text-muted-foreground">
                  No analyses run yet.
                  {canAnalyse && " Use the Analyse button to start one."}
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Risk</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Started</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-medium">
                          <Link
                            href={`/analysis/${job.id}`}
                            className="hover:underline"
                          >
                            {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
                          </Link>
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
                          {formatDate(job.started_at ?? job.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Extracted text note */}
          <Card>
            <CardContent className="p-6">
              <button
                type="button"
                onClick={() => setShowText((v) => !v)}
                className="flex items-center gap-1 text-sm font-medium hover:text-primary"
                aria-expanded={showText}
              >
                <ChevronDown
                  className={cn(
                    "h-4 w-4 transition-transform",
                    showText && "rotate-180",
                  )}
                />
                Extracted text
              </button>
              {showText && (
                <>
                  <Separator className="my-4" />
                  <p className="text-sm text-muted-foreground">
                    The full extracted text of this document is processed
                    internally by the analysis agents and is not exposed through
                    the API for security and size reasons. To read the document,
                    use{" "}
                    <span className="font-medium text-foreground">
                      View Original
                    </span>
                    .
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <AnalyseDialog
        open={analyseOpen}
        onOpenChange={setAnalyseOpen}
        documentId={doc.id}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/documents"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Documents
    </Link>
  );
}
