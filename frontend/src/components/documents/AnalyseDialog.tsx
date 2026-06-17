"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { analysisApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import type { JobType } from "@/types";

const JOB_TYPES: { value: JobType; label: string; description: string }[] = [
  {
    value: "contract_review",
    label: "Contract Review",
    description:
      "Clause-by-clause review of indemnity, liability, IP, termination and more.",
  },
  {
    value: "due_diligence",
    label: "Due Diligence",
    description:
      "Surface obligations, dependencies and red flags for a transaction.",
  },
  {
    value: "reg_compliance",
    label: "Regulatory Compliance",
    description:
      "Check the document against applicable Indian statutes and regulations.",
  },
  {
    value: "risk_assessment",
    label: "Risk Assessment",
    description:
      "Score and prioritise legal risk across the whole document.",
  },
];

export interface AnalyseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
}

export function AnalyseDialog({
  open,
  onOpenChange,
  documentId,
}: AnalyseDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const notify = useUIStore((s) => s.addNotification);

  const [jobType, setJobType] = useState<JobType>("contract_review");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setJobType("contract_review");
      setSubmitting(false);
    }
  }, [open]);

  async function handleStart() {
    if (!documentId) return;
    setSubmitting(true);
    try {
      const job = await analysisApi.createJob({
        document_id: documentId,
        job_type: jobType,
      });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      notify({
        type: "success",
        message: "Analysis started — agents are reviewing your document.",
      });
      onOpenChange(false);
      router.push(`/analysis/${job.id}`);
    } catch (error) {
      setSubmitting(false);
      notify({ type: "error", message: getApiErrorMessage(error) });
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !submitting && onOpenChange(next)}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start Analysis</DialogTitle>
          <DialogDescription>
            Choose the type of analysis to run on this document.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2" role="radiogroup" aria-label="Analysis type">
          {JOB_TYPES.map((t) => {
            const selected = jobType === t.value;
            return (
              <button
                key={t.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setJobType(t.value)}
                disabled={submitting}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors",
                  selected
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "hover:border-primary/40",
                )}
              >
                <p className="text-sm font-medium">{t.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {t.description}
                </p>
              </button>
            );
          })}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button onClick={handleStart} disabled={submitting || !documentId}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitting ? "Starting…" : "Start Analysis"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
