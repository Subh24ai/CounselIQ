"use client";

import { ErrorFallback } from "@/components/shared/ErrorFallback";

// App-section boundary: rendered inside the (app) layout, so the Sidebar and
// Header stay visible and navigation keeps working — only the content area
// shows the error state.
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <ErrorFallback error={error} reset={reset} contained />;
}
