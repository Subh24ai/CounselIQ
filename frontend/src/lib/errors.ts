import { isAxiosError } from "axios";

interface ValidationErrorItem {
  msg?: string;
}

interface ApiErrorBody {
  detail?: string | ValidationErrorItem[];
}

/**
 * Extract a human-readable message from an unknown error, understanding the
 * shapes FastAPI returns: ``{detail: "..."}`` for HTTPException and
 * ``{detail: [{msg, loc, type}]}`` for request-validation failures.
 */
export function getApiErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (isAxiosError<ApiErrorBody>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (first?.msg) return first.msg;
    }
    if (!error.response) {
      return "Cannot reach the server. Check your connection and try again.";
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
