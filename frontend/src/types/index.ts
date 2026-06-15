// Shared domain types for the CounselIQ frontend.
// These mirror the backend API contracts.

export type UserRole = "admin" | "counsel" | "analyst" | "viewer";

export interface Organisation {
  id: string;
  name: string;
  /** Corporate Identification Number (Indian MCA). */
  cin: string | null;
  industry: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface User {
  id: string;
  organisationId: string;
  email: string;
  fullName: string;
  role: UserRole;
  isActive: boolean;
  createdAt: string;
  lastLoginAt: string | null;
}

export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "ocr_complete"
  | "analysed"
  | "failed";

export interface Document {
  id: string;
  organisationId: string;
  uploadedById: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  s3Key: string;
  status: DocumentStatus;
  pageCount: number | null;
  createdAt: string;
  updatedAt: string;
}

export type AnalysisJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface AnalysisJob {
  id: string;
  documentId: string;
  organisationId: string;
  status: AnalysisJobStatus;
  /** Celery task identifier for tracking. */
  taskId: string | null;
  progress: number;
  riskScore: number | null;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export type RiskSeverity = "low" | "medium" | "high" | "critical";

export interface RiskFlag {
  id: string;
  analysisJobId: string;
  documentId: string;
  severity: RiskSeverity;
  category: string;
  title: string;
  description: string;
  /** Statute or regulation referenced, e.g. "Companies Act, 2013 s.149". */
  citation: string | null;
  pageNumber: number | null;
  resolved: boolean;
  createdAt: string;
}

export type AuditAction =
  | "document.uploaded"
  | "document.deleted"
  | "analysis.started"
  | "analysis.completed"
  | "risk.resolved"
  | "user.login"
  | "user.logout";

export interface AuditEntry {
  id: string;
  organisationId: string;
  actorId: string | null;
  action: AuditAction;
  resourceType: string;
  resourceId: string | null;
  metadata: Record<string, unknown>;
  ipAddress: string | null;
  createdAt: string;
}

export interface AuthTokens {
  accessToken: string;
  tokenType: "bearer";
  expiresIn: number;
}
