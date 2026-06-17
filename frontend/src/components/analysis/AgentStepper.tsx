import { Fragment } from "react";
import { Check, Loader2, Minus, X, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AgentStep } from "@/types";

const AGENTS: { key: string; label: string }[] = [
  { key: "extractor", label: "Extractor" },
  { key: "risk_scorer", label: "Risk Scorer" },
  { key: "researcher", label: "Researcher" },
  { key: "drafter", label: "Drafter" },
  { key: "synthesiser", label: "Synthesiser" },
];

type NodeState = "completed" | "failed" | "skipped" | "active" | "pending";

function nodeState(
  agentKey: string,
  steps: AgentStep[],
  currentAgent: string | null,
): NodeState {
  // Use the most recent recorded step for this agent.
  const step = [...steps].reverse().find((s) => s.agent === agentKey);
  if (step?.status === "completed") return "completed";
  if (step?.status === "failed") return "failed";
  if (step?.status === "skipped") return "skipped";
  if (currentAgent === agentKey) return "active";
  return "pending";
}

const NODE_STYLES: Record<
  NodeState,
  { circle: string; label: string; icon: LucideIcon | null; spin?: boolean }
> = {
  completed: {
    circle: "border-emerald-500 bg-emerald-500 text-white",
    label: "text-foreground",
    icon: Check,
  },
  failed: {
    circle: "border-destructive bg-destructive text-white",
    label: "text-destructive",
    icon: X,
  },
  skipped: {
    circle: "border-border bg-muted text-muted-foreground",
    label: "text-muted-foreground",
    icon: Minus,
  },
  active: {
    circle: "border-blue-500 bg-blue-500 text-white animate-pulse",
    label: "text-blue-500 font-medium",
    icon: Loader2,
    spin: true,
  },
  pending: {
    circle: "border-border bg-background text-muted-foreground",
    label: "text-muted-foreground",
    icon: null,
  },
};

export interface AgentStepperProps {
  steps: AgentStep[];
  currentAgent: string | null;
}

export function AgentStepper({ steps, currentAgent }: AgentStepperProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start">
      {AGENTS.map((agent, index) => {
        const state = nodeState(agent.key, steps, currentAgent);
        const style = NODE_STYLES[state];
        const Icon = style.icon;
        return (
          <Fragment key={agent.key}>
            {index > 0 && (
              <div
                aria-hidden
                className="ml-5 h-6 w-px bg-border sm:ml-0 sm:mt-5 sm:h-px sm:flex-1"
              />
            )}
            <div className="flex items-center gap-3 sm:flex-col sm:gap-2 sm:px-1 sm:text-center">
              <span
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                  style.circle,
                )}
              >
                {Icon ? (
                  <Icon className={cn("h-5 w-5", style.spin && "animate-spin")} />
                ) : (
                  <span className="text-sm font-medium">{index + 1}</span>
                )}
              </span>
              <span className={cn("text-sm", style.label)}>{agent.label}</span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
