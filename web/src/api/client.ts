import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const BASE_URL = "/api";

export const client = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

function getCsrfToken(): string | undefined {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; csrf_token=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift();
}

// Attach CSRF header to all state-changing requests
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const method = (config.method ?? "").toLowerCase();
  if (["post", "put", "patch", "delete"].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) {
      config.headers["X-CSRF-Token"] = csrf;
    }
  }
  return config;
});

let isRefreshing = false;
let refreshQueue: Array<(ok: boolean) => void> = [];

// Auto-refresh on 401
client.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    // Normalize FastAPI validation errors to string to prevent React rendering crashes
    if (error.response?.data && typeof error.response.data === "object") {
      const data = error.response.data as any;
      if (Array.isArray(data.detail)) {
        data.detail = data.detail.map((err: any) => err.msg || JSON.stringify(err)).join(", ");
      }
    }

    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (
      error.response?.status === 401 &&
      !original._retry &&
      !original.url?.includes("/auth/")
    ) {
      original._retry = true;
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push((ok) => {
            if (ok) resolve(client(original));
            else reject(error);
          });
        });
      }
      isRefreshing = true;
      try {
        await client.post("/auth/refresh");
        refreshQueue.forEach((cb) => cb(true));
        refreshQueue = [];
        return client(original);
      } catch {
        refreshQueue.forEach((cb) => cb(false));
        refreshQueue = [];
        window.location.href = "/login";
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

export type ApiError = { detail: string; code?: string };

export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiError | undefined;
    return data?.detail ?? err.message;
  }
  return String(err);
}
