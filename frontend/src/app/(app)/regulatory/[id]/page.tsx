"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  SearchX,
} from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { regulatoryApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import type { AffectedDocumentMatch } from "@/types";

function BackLink() {
  return (
    <Link
      href="/regulatory"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Regulatory
    </Link>
  );
}

function similarityTone(score: number): string {
  if (score >= 0.75) return "text-destructive";
  if (score >= 0.65) return "text-amber-500";
  return "text-muted-foreground";
}

export default function RegulatoryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();
  const notify = useUIStore((s) => s.addNotification);
  const role = useAuthStore((s) => s.user?.role);
  const canManage = role === "org_admin" || role === "compliance_officer";

  const updateQuery = useQuery({
    queryKey: ["regulatory", "update", id],
    queryFn: () => regulatoryApi.getUpdate(id),
  });
  const impactQuery = useQuery({
    queryKey: ["regulatory", "impact", id],
    queryFn: () => regulatoryApi.getImpact(id),
  });

  const markProcessed = useMutation({
    mutationFn: () => regulatoryApi.markProcessed(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["regulatory"] });
      notify({ type: "success", message: "Marked as reviewed." });
    },
    onError: (error) => {
      notify({ type: "error", message: getApiErrorMessage(error) });
    },
  });

  if (updateQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading update…" />
      </div>
    );
  }

  const update = updateQuery.data;
  if (updateQuery.isError || !update) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            This regulatory update could not be found.
          </CardContent>
        </Card>
      </div>
    );
  }

  const affected = impactQuery.data?.affected_documents ?? [];

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{update.source ?? "other"}</Badge>
            {update.is_processed ? (
              <Badge variant="success">Reviewed</Badge>
            ) : (
              <Badge variant="warning">New</Badge>
            )}
            <span className="text-xs text-muted-foreground">
              {formatDate(update.published_date)}
            </span>
          </div>
          <h2 className="text-xl font-semibold">{update.title}</h2>
        </div>

        {canManage && !update.is_processed && (
          <Button
            variant="outline"
            onClick={() => markProcessed.mutate()}
            disabled={markProcessed.isPending}
          >
            {markProcessed.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            )}
            Mark as Reviewed
          </Button>
        )}
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          {update.summary && (
            <p className="text-sm leading-relaxed">{update.summary}</p>
          )}
          {update.full_text && (
            <div>
              <h3 className="mb-1 text-sm font-semibold">Full text</h3>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {update.full_text}
              </p>
            </div>
          )}
          {update.url && (
            <a
              href={update.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            >
              <ExternalLink className="h-4 w-4" />
              View source
            </a>
          )}
        </CardContent>
      </Card>

      <div>
        <h3 className="mb-3 text-lg font-semibold">Affected Documents</h3>

        {impactQuery.isLoading ? (
          <div className="flex h-32 items-center justify-center">
            <LoadingSpinner label="Matching your contracts…" />
          </div>
        ) : impactQuery.isError ? (
          <Card>
            <CardContent className="p-6 text-sm text-destructive">
              Couldn&apos;t compute impact. Please retry.
            </CardContent>
          </Card>
        ) : affected.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <EmptyState
                icon={SearchX}
                title="No matching clauses found"
                description="None of your current contracts have clauses semantically similar to this update."
              />
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {affected.map((match) => (
              <AffectedDocumentRow key={match.document_id} match={match} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AffectedDocumentRow({ match }: { match: AffectedDocumentMatch }) {
  const pct = Math.round(match.similarity_score * 100);
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
          <Link
            href={`/documents/${match.document_id}`}
            className="font-medium hover:underline"
          >
            {match.document_name}
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span
              className={cn(
                "text-sm font-semibold tabular-nums",
                similarityTone(match.similarity_score),
              )}
            >
              {pct}%
            </span>
          </div>
        </div>

        {match.matched_clause_excerpt && (
          <blockquote className="border-l-2 border-muted-foreground/30 pl-3 text-sm italic text-muted-foreground">
            {match.matched_clause_excerpt}
            {match.matched_clause_excerpt.length >= 200 ? "…" : ""}
          </blockquote>
        )}
      </CardContent>
    </Card>
  );
}
