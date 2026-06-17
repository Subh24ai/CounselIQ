"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { reviewsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import type { ReviewSubmitRequest, ReviewSummaryResponse } from "@/types";

type Decision = ReviewSubmitRequest["status"]; // approved | rejected

export interface SubmitReviewBarProps {
  jobId: string;
  summary: ReviewSummaryResponse | undefined;
}

export function SubmitReviewBar({ jobId, summary }: SubmitReviewBarProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const addNotification = useUIStore((s) => s.addNotification);

  const [dialog, setDialog] = useState<Decision | null>(null);
  const [notes, setNotes] = useState("");

  const criticalOpen = summary?.critical_open ?? 0;
  const approveDisabled = !summary || criticalOpen > 0;

  const submitReview = useMutation({
    mutationFn: (vars: { status: Decision; notes: string | null }) =>
      reviewsApi.submitReview(jobId, { status: vars.status, notes: vars.notes }),
    onSuccess: (_data, vars) => {
      addNotification({
        type: "success",
        message:
          vars.status === "approved"
            ? "Review approved — analysis marked completed."
            : "Review rejected — sent back for re-analysis.",
      });
      setDialog(null);
      // Refresh the report/job/review so the destination view is up to date.
      void queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      void queryClient.invalidateQueries({ queryKey: ["report", jobId] });
      void queryClient.invalidateQueries({ queryKey: ["review", jobId] });
      router.push(`/analysis/${jobId}`);
    },
    onError: (error) => {
      // Surface the exact backend message (e.g. the 422 critical-flag guard)
      // and keep the dialog open so the reviewer can react.
      addNotification({ type: "error", message: getApiErrorMessage(error) });
    },
  });

  const approvePending =
    submitReview.isPending && submitReview.variables?.status === "approved";
  const rejectPending =
    submitReview.isPending && submitReview.variables?.status === "rejected";

  function openDialog(decision: Decision) {
    setNotes("");
    setDialog(decision);
  }

  return (
    <div className="sticky bottom-0 z-10 -mx-6 border-t bg-background/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {summary ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-medium">{summary.open} open</span>
            <Dot />
            <Muted>{summary.accepted} accepted</Muted>
            <Dot />
            <Muted>{summary.rejected} rejected</Muted>
            <Dot />
            <Muted>{summary.resolved} resolved</Muted>
            <Dot />
            <span
              className={cn(
                criticalOpen > 0
                  ? "font-semibold text-destructive"
                  : "font-medium text-emerald-600",
              )}
            >
              {criticalOpen} critical open
            </span>
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">Loading counts…</span>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {criticalOpen > 0 && (
            <span className="flex items-center gap-1 text-xs text-amber-600">
              <AlertTriangle className="h-3.5 w-3.5" />
              Resolve {criticalOpen} critical flag
              {criticalOpen === 1 ? "" : "s"} before approving
            </span>
          )}

          <Button
            variant="outline"
            onClick={() => openDialog("rejected")}
            disabled={submitReview.isPending}
          >
            Reject Review
          </Button>

          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={approveDisabled ? 0 : -1}>
                  <Button
                    onClick={() => openDialog("approved")}
                    disabled={approveDisabled || submitReview.isPending}
                  >
                    Approve Review
                  </Button>
                </span>
              </TooltipTrigger>
              {approveDisabled && (
                <TooltipContent className="max-w-60">
                  {criticalOpen > 0
                    ? `Resolve ${criticalOpen} critical flag${
                        criticalOpen === 1 ? "" : "s"
                      } before approving.`
                    : "Flag counts are still loading."}
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {/* Approve confirmation */}
      <Dialog
        open={dialog === "approved"}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve this review?</DialogTitle>
            <DialogDescription>
              This will mark the analysis as completed and cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes for the record…"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialog(null)}
              disabled={submitReview.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() =>
                submitReview.mutate({
                  status: "approved",
                  notes: notes.trim() || null,
                })
              }
              disabled={submitReview.isPending}
            >
              {approvePending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Confirm approval
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject confirmation — notes required */}
      <Dialog
        open={dialog === "rejected"}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send this back for re-analysis?</DialogTitle>
            <DialogDescription>
              Explain why so the team can address it before the next pass.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Reason for rejection (required)…"
            aria-label="Rejection reason"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialog(null)}
              disabled={submitReview.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                submitReview.mutate({
                  status: "rejected",
                  notes: notes.trim(),
                })
              }
              disabled={submitReview.isPending || !notes.trim()}
            >
              {rejectPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Confirm rejection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Dot() {
  return <span className="text-muted-foreground">·</span>;
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}
