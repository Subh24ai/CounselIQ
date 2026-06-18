"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ErrorFallbackProps {
  error: Error & { digest?: string };
  reset: () => void;
  /** Constrain to the content area (app boundary) vs fill the viewport (root). */
  contained?: boolean;
}

/**
 * Calm, consistent error UI shared by every Next.js error boundary. The raw
 * error message is shown only in development; in production users see a generic
 * message while details go to logs (and, later, an error-tracking service).
 */
export function ErrorFallback({ error, reset, contained = false }: ErrorFallbackProps) {
  useEffect(() => {
    // Structured shape so this is trivial to forward to Sentry/Datadog later.
    console.error("[error-boundary]", {
      message: error?.message,
      digest: error?.digest,
      stack: error?.stack,
    });
  }, [error]);

  const isDev = process.env.NODE_ENV === "development";

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 p-6 text-center",
        contained ? "min-h-[50vh]" : "min-h-screen",
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden />
      </div>

      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          An unexpected error occurred. You can try again, or head back to your
          dashboard.
        </p>
      </div>

      {isDev && error?.message && (
        <pre className="max-w-xl overflow-auto rounded-md bg-muted p-3 text-left text-xs text-muted-foreground">
          {error.message}
          {error.digest ? `\n\ndigest: ${error.digest}` : ""}
        </pre>
      )}

      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button onClick={reset}>Try again</Button>
        <Button asChild variant="outline">
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
