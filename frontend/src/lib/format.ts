import { format, formatDistanceToNow, parseISO } from "date-fns";

/** Format an ISO timestamp as a short absolute date, e.g. "16 Jun 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "dd MMM yyyy");
  } catch {
    return "—";
  }
}

/** Format an ISO timestamp as a relative time, e.g. "3 hours ago". */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return "—";
  }
}

/**
 * Render a 0-100 risk score to 1 decimal place, or an em dash when not yet
 * computed. 1 decimal everywhere keeps tables, the gauge, and the summary text
 * in agreement (e.g. 71.8 never appears as 72 in one place and 71.8 in another).
 */
export function formatRiskScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return score.toFixed(1);
}

/** Tailwind text colour class for a risk score band (0-30 / 31-60 / 61-100). */
export function riskScoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score < 30) return "text-emerald-500";
  if (score <= 60) return "text-amber-500";
  return "text-destructive";
}
