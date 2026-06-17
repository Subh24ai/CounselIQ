"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Lightbulb, Loader2, ScrollText } from "lucide-react";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { reviewsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import type {
  FlagSeverity,
  Review,
  RiskFlag,
  RiskFlagUpdateRequest,
} from "@/types";

type FlagDecision = RiskFlagUpdateRequest["status"]; // accepted | rejected | resolved

const SEVERITY_BORDER: Record<FlagSeverity, string> = {
  critical: "border-l-destructive",
  high: "border-l-orange-500",
  medium: "border-l-amber-500",
  low: "border-l-muted-foreground/40",
};

// Muted, colour-coded styling once a reviewer has acted on a flag.
const DECISION_STYLE: Record<FlagDecision, { border: string; bg: string }> = {
  accepted: { border: "border-l-emerald-500", bg: "bg-emerald-500/5" },
  rejected: { border: "border-l-destructive", bg: "bg-destructive/5" },
  resolved: { border: "border-l-blue-500", bg: "bg-blue-500/5" },
};

const ACTIONS: { status: FlagDecision; label: string }[] = [
  { status: "accepted", label: "Accept" },
  { status: "rejected", label: "Reject" },
  { status: "resolved", label: "Resolve" },
];

function humanize(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export interface RiskFlagCardProps {
  flag: RiskFlag;
  /** Display-only (e.g. the analysis report). No actions are rendered. */
  readonly?: boolean;
  /** Required to enable review actions — keys the optimistic cache update. */
  jobId?: string;
}

export function RiskFlagCard({ flag, readonly, jobId }: RiskFlagCardProps) {
  const queryClient = useQueryClient();
  const addNotification = useUIStore((s) => s.addNotification);

  const [showReasoning, setShowReasoning] = useState(false);
  // Seed the textarea from the persisted note so it survives a page reload.
  const [noteDraft, setNoteDraft] = useState(flag.notes ?? "");
  // Lets the reviewer re-open the action buttons on an already-decided flag.
  const [overrideActions, setOverrideActions] = useState(false);
  // The note value last persisted, so blur-saves don't fire redundant requests.
  const lastSavedNote = useRef(flag.notes ?? "");

  const severity = (flag.severity ?? "low") as FlagSeverity;
  const isOpen = flag.status === "open";
  const isCriticalOpen = isOpen && severity === "critical";
  const interactive = !readonly && !!jobId;
  const showActions = interactive && (isOpen || overrideActions);
  const confidencePct =
    flag.confidence_score != null
      ? Math.round(flag.confidence_score * 100)
      : null;

  const updateFlag = useMutation({
    mutationFn: (vars: { status: FlagDecision; notes: string | null }) =>
      reviewsApi.updateFlag(flag.id, {
        status: vars.status,
        notes: vars.notes,
      }),
    onMutate: async (vars) => {
      if (!jobId) return { previous: undefined };
      // Cancel in-flight refetches so they can't clobber the optimistic value.
      await queryClient.cancelQueries({ queryKey: ["review", jobId] });
      const previous = queryClient.getQueryData<Review>(["review", jobId]);
      queryClient.setQueryData<Review>(["review", jobId], (old) =>
        old
          ? {
              ...old,
              risk_flags: old.risk_flags.map((f) =>
                f.id === flag.id ? { ...f, status: vars.status } : f,
              ),
            }
          : old,
      );
      return { previous };
    },
    onError: (error, _vars, context) => {
      // Roll back to the exact pre-mutation snapshot.
      if (jobId && context?.previous) {
        queryClient.setQueryData(["review", jobId], context.previous);
      }
      addNotification({
        type: "error",
        message: `Failed to update flag: ${getApiErrorMessage(error)}`,
      });
    },
    onSuccess: () => {
      setOverrideActions(false);
      if (jobId) {
        void queryClient.invalidateQueries({
          queryKey: ["review-summary", jobId],
        });
      }
    },
    onSettled: () => {
      // Reconcile the optimistic value with server truth.
      if (jobId) {
        void queryClient.invalidateQueries({ queryKey: ["review", jobId] });
      }
    },
  });

  function act(status: FlagDecision) {
    const notes = noteDraft.trim() || null;
    lastSavedNote.current = noteDraft.trim();
    updateFlag.mutate({ status, notes });
  }

  // Persist a note edit on an already-decided flag without changing its status.
  function handleNoteBlur() {
    if (!interactive || isOpen) return; // open flags: note rides with the action
    const trimmed = noteDraft.trim();
    if (trimmed === lastSavedNote.current) return;
    lastSavedNote.current = trimmed;
    updateFlag.mutate({ status: flag.status as FlagDecision, notes: trimmed || null });
  }

  const decisionStyle =
    !isOpen && flag.status in DECISION_STYLE
      ? DECISION_STYLE[flag.status as FlagDecision]
      : null;

  return (
    <div
      className={cn(
        "rounded-lg border border-l-4 bg-card p-4 shadow-sm transition-colors",
        decisionStyle ? decisionStyle.border : SEVERITY_BORDER[severity],
        decisionStyle?.bg,
        isCriticalOpen && "ring-2 ring-destructive/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={severity} />
        {flag.category && (
          <Badge variant="outline">{humanize(flag.category)}</Badge>
        )}
        {!isOpen && <StatusBadge status={flag.status} />}
        {confidencePct != null && (
          <span className="ml-auto text-xs text-muted-foreground">
            {confidencePct}% confidence
          </span>
        )}
      </div>

      <h3 className="mt-2 font-semibold">{flag.title}</h3>

      {flag.description && (
        <p className="mt-1 text-sm text-muted-foreground">{flag.description}</p>
      )}

      {flag.cited_regulation && (
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-xs">
          <ScrollText className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-medium">{flag.cited_regulation}</span>
        </div>
      )}

      {flag.suggested_action && (
        <div className="mt-3 flex gap-2 rounded-md border border-primary/20 bg-primary/5 p-3">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div>
            <p className="text-xs font-medium text-primary">Suggested action</p>
            <p className="mt-0.5 text-sm">{flag.suggested_action}</p>
          </div>
        </div>
      )}

      {flag.agent_reasoning && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowReasoning((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
            aria-expanded={showReasoning}
          >
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                showReasoning && "rotate-180",
              )}
            />
            Why this matters
          </button>
          {showReasoning && (
            <p className="mt-2 rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
              {flag.agent_reasoning}
            </p>
          )}
        </div>
      )}

      {interactive && (
        <div className="mt-4 space-y-2">
          <Input
            value={noteDraft}
            onChange={(e) => setNoteDraft(e.target.value)}
            onBlur={handleNoteBlur}
            placeholder="Optional notes for this flag…"
            disabled={updateFlag.isPending}
            aria-label="Flag notes"
          />

          {showActions ? (
            <div className="flex flex-wrap gap-2">
              {ACTIONS.map(({ status, label }) => {
                const pendingThis =
                  updateFlag.isPending &&
                  updateFlag.variables?.status === status;
                return (
                  <Button
                    key={status}
                    size="sm"
                    variant="outline"
                    onClick={() => act(status)}
                    disabled={updateFlag.isPending}
                  >
                    {pendingThis ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : status === "accepted" ? (
                      <Check className="mr-1 h-4 w-4" />
                    ) : null}
                    {label}
                  </Button>
                );
              })}
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <StatusBadge status={flag.status} />
              <button
                type="button"
                onClick={() => setOverrideActions(true)}
                className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                Change
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
