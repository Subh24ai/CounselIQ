import type { DocumentStatus, JobStatus } from "@/types";

// Document statuses from which a (new) analysis can be started. Mirrors the
// backend's ANALYSABLE_DOCUMENT_STATUSES: a *completed* document can be
// re-analysed any number of times (e.g. after an amendment, or to run a
// different job type).
export const ANALYSABLE_DOCUMENT_STATUSES: DocumentStatus[] = [
  "extracted",
  "completed",
];

export function isAnalysableStatus(status: DocumentStatus): boolean {
  return ANALYSABLE_DOCUMENT_STATUSES.includes(status);
}

// Job statuses that mean an analysis is currently running for the document —
// while one of these is active, a new job must not be started. This is the
// SINGLE authoritative "in progress" signal; the document's own status is a
// denormalised convenience that can be left stale (e.g. a crashed worker
// orphaned in 'analysing') and must never gate re-analysis on its own.
export const IN_PROGRESS_JOB_STATUSES: JobStatus[] = ["pending", "running"];

export function isJobInProgress(status: JobStatus): boolean {
  return IN_PROGRESS_JOB_STATUSES.includes(status);
}

export function hasActiveAnalysisJob(jobs: { status: JobStatus }[]): boolean {
  return jobs.some((job) => isJobInProgress(job.status));
}

/**
 * Whether a NEW analysis can be started for a document. A document is
 * re-analysable once it has been extracted; the existence of any prior job
 * proves extraction succeeded (a job cannot be created otherwise), so the
 * document stays re-analysable even when its status is stale — 'analysing'
 * (crashed worker) or 'failed' (failed run). Only an active pending/running
 * job blocks a new analysis.
 */
export function canStartAnalysis(
  documentStatus: DocumentStatus,
  jobs: { status: JobStatus }[],
): boolean {
  if (hasActiveAnalysisJob(jobs)) return false;
  return isAnalysableStatus(documentStatus) || jobs.length > 0;
}
