// Shared domain types for the CounselIQ frontend.
// Field names mirror the backend JSON contracts exactly (snake_case).

// --- Auth & users -----------------------------------------------------------
export type UserRole =
  | "org_admin"
  | "legal_counsel"
  | "compliance_officer"
  | "viewer";

export interface User {
  id: string;
  organisation_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

export interface Organisation {
  id: string;
  name: string;
  domain: string | null;
  plan: string;
  is_active: boolean;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  organisation_name: string;
  domain?: string | null;
  plan?: string;
  email: string;
  password: string;
  full_name: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// --- Invitations ------------------------------------------------------------
export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

// Roles an org_admin may assign via an invitation (org_admin excluded).
export type InvitableRole = "legal_counsel" | "compliance_officer" | "viewer";

export interface Invitation {
  id: string;
  organisation_id: string;
  email: string;
  role: UserRole;
  status: InvitationStatus;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  invite_link: string;
}

export interface InvitationCreate {
  email: string;
  role: InvitableRole;
}

export interface InvitationAcceptRequest {
  token: string;
  full_name: string;
  password: string;
  confirm_password: string;
}

export interface InvitationAcceptResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
  organisation: Organisation;
}

export interface InvitationValidateResponse {
  email: string;
  role: UserRole;
  organisation_name: string;
  expires_at: string;
}

// --- Documents --------------------------------------------------------------
export type DocumentStatus =
  | "uploaded"
  | "queued"
  | "extracting"
  | "extracted"
  | "analysing"
  | "completed"
  | "failed"
  | "deleted";

export type DocumentType =
  | "vendor_contract"
  | "employment"
  | "nda"
  | "msa"
  | "policy"
  | "regulatory"
  | "other";

export interface Document {
  id: string;
  name: string;
  original_filename: string | null;
  document_type: DocumentType;
  status: DocumentStatus;
  file_size_bytes: number | null;
  page_count: number | null;
  mime_type: string | null;
  uploaded_by: string | null;
  created_at: string;
  presigned_url: string | null;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  textract_job_id: string | null;
  page_count: number | null;
  updated_at: string;
}

// --- Analysis ---------------------------------------------------------------
export type JobStatus =
  | "pending"
  | "running"
  | "awaiting_review"
  | "completed"
  | "failed";

export type JobType =
  | "contract_review"
  | "due_diligence"
  | "reg_compliance"
  | "risk_assessment";

export interface AgentStep {
  agent: string;
  status: "started" | "completed" | "failed" | "skipped";
  input_summary: string;
  output_summary: string;
  confidence: number;
  duration_ms: number;
  timestamp: string;
}

export interface AnalysisJob {
  id: string;
  document_id: string;
  status: JobStatus;
  job_type: JobType;
  overall_risk_score: number | null;
  agent_trace: AgentStep[];
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AnalysisJobListResponse {
  items: AnalysisJob[];
  total: number;
  page: number;
  page_size: number;
}

export interface AnalysisJobCreate {
  document_id: string;
  job_type: JobType;
}

// --- Risk flags -------------------------------------------------------------
export type FlagCategory =
  | "indemnity"
  | "liability_cap"
  | "ip_assignment"
  | "auto_renewal"
  | "jurisdiction"
  | "termination"
  | "payment_terms"
  | "confidentiality"
  | "data_protection"
  | "regulatory";

export type FlagSeverity = "critical" | "high" | "medium" | "low";

export type FlagStatus = "open" | "accepted" | "rejected" | "resolved";

export interface RiskFlag {
  id: string;
  category: FlagCategory | string | null;
  severity: FlagSeverity | null;
  title: string;
  description: string | null;
  suggested_action: string | null;
  agent_reasoning: string | null;
  cited_regulation: string | null;
  confidence_score: number | null;
  status: FlagStatus;
  notes: string | null;
}

export interface RiskFlagUpdateRequest {
  status: "accepted" | "rejected" | "resolved";
  notes?: string | null;
}

export interface DraftedAlternative {
  clause_index?: number;
  original_clause_type?: string;
  alternative_text?: string;
  changes_summary?: string | string[];
  negotiation_note?: string;
  fallback_position?: string;
}

export interface ResearchFinding {
  risk_flag_index?: number;
  regulation_name?: string;
  section?: string;
  relevance?: string;
  implication?: string;
  source_hint?: string;
}

export interface AnalysisReportResponse {
  job: AnalysisJob;
  risk_flags: RiskFlag[];
  drafted_alternatives: DraftedAlternative[];
  research_findings: ResearchFinding[];
  summary_report: string | null;
  clauses_count: number;
}

// --- Reviews ----------------------------------------------------------------
export type ReviewStatus = "pending" | "in_progress" | "approved" | "rejected";

export interface Review {
  id: string;
  analysis_job_id: string;
  reviewed_by: string | null;
  status: ReviewStatus;
  notes: string | null;
  approved_at: string | null;
  created_at: string;
  risk_flags: RiskFlag[];
}

export interface ReviewStartResponse {
  review_id: string;
  analysis_job_id: string;
  status: string;
  created_at: string;
}

export interface ReviewSubmitRequest {
  status: "approved" | "rejected";
  notes?: string | null;
}

export interface ReviewSummaryResponse {
  total_flags: number;
  accepted: number;
  rejected: number;
  resolved: number;
  open: number;
  critical_open: number;
}

// --- Regulatory monitor -----------------------------------------------------
export type RegulatorySource =
  | "SEBI"
  | "IRDAI"
  | "MCA"
  | "RBI"
  | "NABH"
  | "other";

export interface RegulatoryUpdate {
  id: string;
  source: RegulatorySource | string | null;
  title: string;
  summary: string | null;
  full_text?: string | null;
  url: string | null;
  published_date: string | null;
  is_processed: boolean;
  created_at: string;
}

export interface RegulatoryUpdateCreate {
  source: string;
  title: string;
  summary: string;
  full_text?: string | null;
  url?: string | null;
  published_date: string; // ISO date (YYYY-MM-DD)
}

export interface RegulatoryUpdateListResponse {
  items: RegulatoryUpdate[];
  total: number;
  page: number;
  page_size: number;
}

export interface AffectedDocumentMatch {
  document_id: string;
  document_name: string;
  similarity_score: number; // 0.0-1.0
  matched_clause_id: string | null;
  matched_clause_excerpt: string | null;
}

export interface RegulatoryImpactResponse {
  regulatory_update: RegulatoryUpdate;
  affected_documents: AffectedDocumentMatch[];
}

// --- WebSocket --------------------------------------------------------------
export interface WebSocketMessage {
  type:
    | "connected"
    | "job_update"
    | "agent_step"
    | "pong"
    | "review_flag_updated"
    | "review_submitted";
  job_id?: string;
  flag_id?: string;
  // job_update carries a JobStatus; review_* events carry a flag/review status.
  status?: JobStatus | string;
  progress?: Record<string, unknown>;
  step?: AgentStep;
  organisation_id?: string;
  user_id?: string;
  timestamp?: string;
}
