import { Badge, type BadgeProps } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

// Maps any job / document / flag / review status or severity to a badge
// variant. Unknown values fall back to a neutral secondary badge.
const VARIANT_MAP: Record<string, BadgeVariant> = {
  // Severities
  critical: "destructive",
  high: "orange",
  medium: "warning",
  low: "secondary",
  // Job statuses
  pending: "secondary",
  running: "info",
  awaiting_review: "warning",
  completed: "success",
  failed: "destructive",
  // Document statuses
  uploaded: "secondary",
  queued: "info",
  extracting: "info",
  extracted: "success",
  analysing: "info",
  // Soft-deleted: muted/neutral, never a failure style.
  deleted: "secondary",
  // Flag statuses
  open: "outline",
  accepted: "success",
  rejected: "destructive",
  resolved: "secondary",
  // Review statuses
  in_progress: "info",
  approved: "success",
};

function humanize(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const variant = VARIANT_MAP[status] ?? "secondary";
  // Running jobs pulse to signal in-flight work.
  const animated = status === "running" || status === "analysing";
  return (
    <Badge
      variant={variant}
      className={cn(animated && "animate-pulse", className)}
    >
      {humanize(status)}
    </Badge>
  );
}
