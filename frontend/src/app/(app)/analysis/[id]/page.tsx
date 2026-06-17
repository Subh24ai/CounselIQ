"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, ScrollText } from "lucide-react";

import { AgentStepper } from "@/components/analysis/AgentStepper";
import { Markdown } from "@/components/analysis/Markdown";
import { RiskFlagCard } from "@/components/analysis/RiskFlagCard";
import { AgentStepTimeline } from "@/components/shared/AgentStepTimeline";
import { EmptyState } from "@/components/shared/EmptyState";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { RiskScoreGauge } from "@/components/shared/RiskScoreGauge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { analysisApi, documentsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import { useWebSocketStore } from "@/store/websocket";
import type {
  AgentStep,
  DraftedAlternative,
  FlagSeverity,
  JobStatus,
  JobType,
  RiskFlag,
} from "@/types";

const AGENT_ORDER = [
  "extractor",
  "risk_scorer",
  "researcher",
  "drafter",
  "synthesiser",
];

const POLL_STATUSES: JobStatus[] = ["pending", "running"];
const REPORTABLE: JobStatus[] = ["awaiting_review", "completed"];
const SEVERITY_ORDER: FlagSeverity[] = ["critical", "high", "medium", "low"];

const JOB_TYPE_LABELS: Record<JobType, string> = {
  contract_review: "Contract Review",
  due_diligence: "Due Diligence",
  reg_compliance: "Regulatory Compliance",
  risk_assessment: "Risk Assessment",
};

const REVIEWER_ROLES = new Set(["legal_counsel", "org_admin"]);

function BackLink() {
  return (
    <Link
      href="/analysis"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Analysis
    </Link>
  );
}

export default function AnalysisJobPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const wsSteps = useWebSocketStore((s) => s.agentSteps[id]);
  const wsStatus = useWebSocketStore((s) => s.jobUpdates[id]);
  const role = useAuthStore((s) => s.user?.role ?? "viewer");

  const jobQuery = useQuery({
    queryKey: ["job", id],
    queryFn: () => analysisApi.getJob(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // WebSocket may have already advanced the status; stop polling then.
      if (wsStatus && REPORTABLE.includes(wsStatus)) return false;
      return status && POLL_STATUSES.includes(status) ? 3000 : false;
    },
  });

  const job = jobQuery.data;
  const effectiveStatus: JobStatus | undefined = wsStatus ?? job?.status;
  const inProgress =
    effectiveStatus !== undefined && POLL_STATUSES.includes(effectiveStatus);
  const reportable =
    effectiveStatus !== undefined && REPORTABLE.includes(effectiveStatus);

  const reportQuery = useQuery({
    queryKey: ["report", id],
    queryFn: () => analysisApi.getReport(id),
    enabled: reportable,
  });

  const documentId = reportQuery.data?.job.document_id ?? job?.document_id;
  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => documentsApi.getDocument(documentId as string),
    enabled: !!documentId,
  });
  const documentName = documentQuery.data?.name;

  if (jobQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading analysis…" />
      </div>
    );
  }

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

  // --- Failed -------------------------------------------------------------
  if (effectiveStatus === "failed") {
    return (
      <div className="space-y-6">
        <BackLink />
        <Card>
          <CardContent className="space-y-2 p-6">
            <h2 className="text-lg font-semibold text-destructive">
              Analysis failed
            </h2>
            <p className="text-sm text-muted-foreground">
              {job.error_message ??
                "Something went wrong while analysing this document."}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- In progress --------------------------------------------------------
  if (inProgress || (!reportable && !reportQuery.data)) {
    const steps: AgentStep[] =
      wsSteps && wsSteps.length > 0 ? wsSteps : job.agent_trace;
    const done = new Set(
      steps.filter((s) => s.status !== "started").map((s) => s.agent),
    );
    const currentAgent = AGENT_ORDER.find((a) => !done.has(a)) ?? null;

    return (
      <div className="space-y-6">
        <BackLink />
        <div>
          <h2 className="text-xl font-semibold">
            {documentName ?? jobTypeLabel}
          </h2>
          <p className="text-sm text-muted-foreground">
            {jobTypeLabel} · Analysis in progress
          </p>
        </div>

        <Card>
          <CardContent className="space-y-8 p-6">
            <AgentStepper steps={steps} currentAgent={currentAgent} />
            <p className="text-center text-sm text-muted-foreground">
              This typically takes 30–90 seconds. Results appear automatically.
            </p>
          </CardContent>
        </Card>

        {steps.length > 0 && (
          <Card>
            <CardContent className="p-6">
              <h3 className="mb-4 text-sm font-semibold">Agent activity</h3>
              <AgentStepTimeline steps={steps} />
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // --- Report (awaiting_review / completed) -------------------------------
  if (reportQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading report…" />
      </div>
    );
  }

  const report = reportQuery.data;
  if (reportQuery.isError || !report) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            The report for this job could not be loaded.
          </CardContent>
        </Card>
      </div>
    );
  }

  const score = report.job.overall_risk_score ?? 0;
  const canReview =
    effectiveStatus === "awaiting_review" && REVIEWER_ROLES.has(role);

  const flagsBySeverity = SEVERITY_ORDER.map((severity) => ({
    severity,
    flags: report.risk_flags.filter((f) => f.severity === severity),
  })).filter((group) => group.flags.length > 0);

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h2 className="text-xl font-semibold">
            {documentName ?? "Analysis Report"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {jobTypeLabel} · {report.clauses_count} clauses ·{" "}
            {report.risk_flags.length} risk flags
          </p>
          <div className="mt-2">
            <StatusPill status={effectiveStatus} />
          </div>
        </div>
        <RiskScoreGauge score={score} size={120} />
      </div>

      <Tabs defaultValue="summary">
        <TabsList className="flex-wrap">
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="flags">
            Risk Flags ({report.risk_flags.length})
          </TabsTrigger>
          <TabsTrigger value="research">
            Research ({report.research_findings.length})
          </TabsTrigger>
          <TabsTrigger value="redlines">
            Suggested Redlines ({report.drafted_alternatives.length})
          </TabsTrigger>
          <TabsTrigger value="trace">Agent Trace</TabsTrigger>
        </TabsList>

        {/* Summary */}
        <TabsContent value="summary">
          <Card>
            <CardContent className="p-6">
              {report.summary_report ? (
                <Markdown>{report.summary_report}</Markdown>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No summary was generated for this analysis.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Risk flags */}
        <TabsContent value="flags" className="space-y-6">
          {canReview && (
            <div className="flex justify-end">
              <Button asChild>
                <Link href={`/reviews/${id}`}>Start Review</Link>
              </Button>
            </div>
          )}
          {report.risk_flags.length === 0 ? (
            <Card>
              <CardContent className="p-6">
                <EmptyState
                  icon={Check}
                  title="No risk flags"
                  description="The agents did not raise any risks for this document."
                />
              </CardContent>
            </Card>
          ) : (
            flagsBySeverity.map((group) => (
              <div key={group.severity} className="space-y-3">
                <h3 className="text-sm font-semibold capitalize text-muted-foreground">
                  {group.severity} ({group.flags.length})
                </h3>
                {group.flags.map((flag: RiskFlag) => (
                  <RiskFlagCard key={flag.id} flag={flag} readonly />
                ))}
              </div>
            ))
          )}
        </TabsContent>

        {/* Research */}
        <TabsContent value="research" className="space-y-3">
          {report.research_findings.length === 0 ? (
            <Card>
              <CardContent className="p-6">
                <EmptyState
                  icon={ScrollText}
                  title="No research findings"
                  description="No regulatory references were attached to this analysis."
                />
              </CardContent>
            </Card>
          ) : (
            report.research_findings.map((finding, index) => (
              <Card key={index}>
                <CardContent className="space-y-2 p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {finding.regulation_name ?? "Regulation"}
                    </Badge>
                    {finding.section && (
                      <Badge variant="outline">{finding.section}</Badge>
                    )}
                  </div>
                  {finding.relevance && (
                    <p className="text-sm">{finding.relevance}</p>
                  )}
                  {finding.implication && (
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">
                        Implication:{" "}
                      </span>
                      {finding.implication}
                    </p>
                  )}
                  {finding.source_hint && (
                    <p className="text-xs text-muted-foreground">
                      Verify at: {finding.source_hint}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        {/* Suggested redlines */}
        <TabsContent value="redlines" className="space-y-4">
          {report.drafted_alternatives.length === 0 ? (
            <Card>
              <CardContent className="p-6">
                <EmptyState
                  icon={ScrollText}
                  title="No suggested redlines"
                  description="No alternative clauses were drafted for this document."
                />
              </CardContent>
            </Card>
          ) : (
            report.drafted_alternatives.map((alt, index) => (
              <RedlineCard key={index} alternative={alt} />
            ))
          )}
        </TabsContent>

        {/* Agent trace */}
        <TabsContent value="trace">
          <Card>
            <CardContent className="p-6">
              <AgentStepTimeline steps={report.job.agent_trace} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatusPill({ status }: { status: JobStatus | undefined }) {
  if (!status) return null;
  const label =
    status === "awaiting_review" ? "Awaiting review" : "Completed";
  return (
    <Badge variant={status === "completed" ? "success" : "warning"}>
      {label}
    </Badge>
  );
}

function normaliseChanges(
  changes: string | string[] | undefined,
): string[] {
  if (!changes) return [];
  if (Array.isArray(changes)) return changes;
  return changes
    .split("\n")
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean);
}

function RedlineCard({ alternative }: { alternative: DraftedAlternative }) {
  const notify = useUIStore((s) => s.addNotification);
  const [copied, setCopied] = useState(false);
  const changes = normaliseChanges(alternative.changes_summary);

  async function copy() {
    if (!alternative.alternative_text) return;
    try {
      await navigator.clipboard.writeText(alternative.alternative_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      notify({ type: "error", message: "Couldn't copy to clipboard." });
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline" className="capitalize">
            {(alternative.original_clause_type ?? "clause").replace(/_/g, " ")}
          </Badge>
          {alternative.alternative_text && (
            <Button variant="ghost" size="sm" onClick={copy}>
              {copied ? (
                <Check className="mr-1 h-4 w-4 text-emerald-500" />
              ) : (
                <Copy className="mr-1 h-4 w-4" />
              )}
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
        </div>

        {alternative.alternative_text && (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-xs leading-relaxed">
            {alternative.alternative_text}
          </pre>
        )}

        {changes.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              What changed
            </p>
            <ul className="mt-1 ml-4 list-disc space-y-1 text-sm">
              {changes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        {alternative.negotiation_note && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Negotiation: </span>
            {alternative.negotiation_note}
          </p>
        )}

        {alternative.fallback_position && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Fallback: </span>
            {alternative.fallback_position}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
