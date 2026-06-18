"use client";

import { ErrorFallback } from "@/components/shared/ErrorFallback";

// global-error catches errors thrown in the root layout itself. It replaces the
// root layout, so it must render its own <html> and <body>.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <ErrorFallback error={error} reset={reset} />
      </body>
    </html>
  );
}
