import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const SIZES = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-10 w-10",
} as const;

export interface LoadingSpinnerProps {
  size?: keyof typeof SIZES;
  className?: string;
  label?: string;
}

export function LoadingSpinner({
  size = "md",
  className,
  label,
}: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-2"
    >
      <Loader2
        className={cn("animate-spin text-muted-foreground", SIZES[size], className)}
      />
      {label && <span className="text-sm text-muted-foreground">{label}</span>}
      <span className="sr-only">Loading</span>
    </div>
  );
}
