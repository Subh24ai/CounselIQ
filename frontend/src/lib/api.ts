import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "@/store/auth";
import type {
  AnalysisJob,
  AnalysisJobCreate,
  AnalysisReportResponse,
  Document,
  DocumentListResponse,
  DocumentStatusResponse,
  LoginRequest,
  RefreshRequest,
  RegisterRequest,
  Review,
  ReviewStartResponse,
  ReviewSubmitRequest,
  ReviewSummaryResponse,
  RiskFlag,
  RiskFlagUpdateRequest,
  TokenResponse,
  User,
} from "@/types";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

/** Pre-configured axios instance for the CounselIQ API. */
export const api: AxiosInstance = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// --- Request interceptor: attach the bearer token from the auth store. ------
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

// --- Response interceptor: transparent 401 -> refresh -> retry-once. --------
// Endpoints whose 401s must not trigger a refresh attempt (would loop).
const NO_REFRESH = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

// Single-flight refresh: concurrent 401s share one refresh request.
let refreshPromise: Promise<string> | null = null;

async function performRefresh(): Promise<string> {
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) throw new Error("No refresh token available");
  // Use a bare axios call so this request is not itself intercepted.
  const { data } = await axios.post<TokenResponse>(
    `${API_BASE}/api/v1/auth/refresh`,
    { refresh_token: refreshToken },
  );
  useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

/**
 * Single-flight access-token refresh. Concurrent callers (the HTTP 401
 * interceptor and the WebSocket store's pre-connect freshness check) share one
 * in-flight refresh request and resolve to the same new access token.
 */
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;

    const status = error.response?.status;
    const url = original?.url ?? "";
    const skipRefresh = NO_REFRESH.some((path) => url.includes(path));

    if (status === 401 && original && !original._retry && !skipRefresh) {
      original._retry = true;
      try {
        const newToken = await refreshAccessToken();
        original.headers.set("Authorization", `Bearer ${newToken}`);
        return api(original);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        if (
          typeof window !== "undefined" &&
          !window.location.pathname.startsWith("/login")
        ) {
          window.location.assign("/login");
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);

// --- Typed API surface ------------------------------------------------------

export const authApi = {
  async register(data: RegisterRequest): Promise<TokenResponse> {
    return (await api.post<TokenResponse>("/auth/register", data)).data;
  },
  async login(data: LoginRequest): Promise<TokenResponse> {
    return (await api.post<TokenResponse>("/auth/login", data)).data;
  },
  async refresh(data: RefreshRequest): Promise<TokenResponse> {
    return (await api.post<TokenResponse>("/auth/refresh", data)).data;
  },
  async logout(): Promise<void> {
    // Best-effort: the local session is cleared regardless of the result.
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore — logout must always succeed locally */
    }
  },
  async getMe(): Promise<User> {
    return (await api.get<User>("/auth/me")).data;
  },
};

export const documentsApi = {
  async uploadDocument(
    formData: FormData,
    onProgress?: (percent: number) => void,
  ): Promise<Document> {
    return (
      await api.post<Document>("/documents/upload", formData, {
        // Let the browser set the multipart boundary.
        headers: { "Content-Type": undefined },
        onUploadProgress: (event) => {
          if (onProgress && event.total) {
            onProgress(Math.round((event.loaded / event.total) * 100));
          }
        },
      })
    ).data;
  },
  async listDocuments(
    page = 1,
    pageSize = 20,
    includeDeleted = false,
  ): Promise<DocumentListResponse> {
    return (
      await api.get<DocumentListResponse>("/documents/", {
        params: { page, page_size: pageSize, include_deleted: includeDeleted },
      })
    ).data;
  },
  async getDocument(id: string): Promise<Document> {
    return (await api.get<Document>(`/documents/${id}`)).data;
  },
  async getDocumentStatus(id: string): Promise<DocumentStatusResponse> {
    return (await api.get<DocumentStatusResponse>(`/documents/${id}/status`))
      .data;
  },
  async deleteDocument(id: string): Promise<void> {
    await api.delete(`/documents/${id}`);
  },
};

interface AnalysisJobListResponseRaw {
  items: AnalysisJob[];
  total: number;
  page: number;
  page_size: number;
}

export const analysisApi = {
  async createJob(data: AnalysisJobCreate): Promise<AnalysisJob> {
    return (await api.post<AnalysisJob>("/analysis/jobs", data)).data;
  },
  async listJobs(page = 1, pageSize = 20): Promise<AnalysisJob[]> {
    const { data } = await api.get<AnalysisJobListResponseRaw>(
      "/analysis/jobs",
      { params: { page, page_size: pageSize } },
    );
    return data.items;
  },
  async getJob(id: string): Promise<AnalysisJob> {
    return (await api.get<AnalysisJob>(`/analysis/jobs/${id}`)).data;
  },
  async getReport(id: string): Promise<AnalysisReportResponse> {
    return (
      await api.get<AnalysisReportResponse>(`/analysis/jobs/${id}/report`)
    ).data;
  },
};

export const reviewsApi = {
  async listReviews(page = 1, pageSize = 100): Promise<Review[]> {
    return (
      await api.get<Review[]>("/reviews/", {
        params: { page, page_size: pageSize },
      })
    ).data;
  },
  async startReview(jobId: string): Promise<ReviewStartResponse> {
    return (
      await api.post<ReviewStartResponse>(`/reviews/jobs/${jobId}/start`)
    ).data;
  },
  async getReview(jobId: string): Promise<Review> {
    return (await api.get<Review>(`/reviews/jobs/${jobId}`)).data;
  },
  async getSummary(jobId: string): Promise<ReviewSummaryResponse> {
    return (
      await api.get<ReviewSummaryResponse>(`/reviews/jobs/${jobId}/summary`)
    ).data;
  },
  async updateFlag(
    flagId: string,
    data: RiskFlagUpdateRequest,
  ): Promise<RiskFlag> {
    return (await api.patch<RiskFlag>(`/reviews/flags/${flagId}`, data)).data;
  },
  async submitReview(
    jobId: string,
    data: ReviewSubmitRequest,
  ): Promise<Review> {
    return (await api.post<Review>(`/reviews/jobs/${jobId}/submit`, data)).data;
  },
};

export default api;
