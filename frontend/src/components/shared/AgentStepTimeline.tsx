import {
  CheckCircle2,
  CircleDashed,
  Loader2,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AgentStep } from "@/types";

const STEP_ICON: Record<AgentStep["status"], LucideIcon> = {
  completed: CheckCircle2,
  failed: XCircle,
  started: Loader2,
  skipped: CircleDashed,
};

const STEP_ICON_COLOR: Record<AgentStep["status"], string> = {
  completed: "text-emerald-500",
  failed: "text-destructive",
  started: "text-blue-500",
  skipped: "text-muted-foreground",
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function humanizeAgent(name: string): string {
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export interface AgentStepTimelineProps {
  steps: AgentStep[];
}

export function AgentStepTimeline({ steps }: AgentStepTimelineProps) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No agent activity recorded yet.
      </p>
    );
  }

  return (
    <ol className="relative space-y-6 border-l border-border pl-6">
      {steps.map((step, index) => {
        const Icon = STEP_ICON[step.status];
        return (
          <li key={`${step.agent}-${index}`} className="relative">
            <span
              className={cn(
                "absolute -left-[31px] flex h-6 w-6 items-center justify-center rounded-full bg-background ring-4 ring-background",
                STEP_ICON_COLOR[step.status],
              )}
            >
              <Icon
                className={cn(
                  "h-5 w-5",
                  step.status === "started" && "animate-spin",
                )}
              />
            </span>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-medium">{humanizeAgent(step.agent)}</span>
                <Badge variant="outline" className="text-xs">
                  {Math.round(step.confidence * 100)}% confidence
                </Badge>
              </div>
              <span className="text-xs text-muted-foreground">
                {formatDuration(step.duration_ms)}
              </span>
            </div>
            {step.output_summary && (
              <p className="mt-1 text-sm text-muted-foreground">
                {step.output_summary}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
