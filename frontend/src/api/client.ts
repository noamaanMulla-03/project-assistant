// ── Axios API Client ─────────────────────────────────────────────────────────
// Configured with cookie credentials and automatic token-refresh on 401.
//
// Architecture:
//   - Access token is stored in a module-level closure (NOT in React state
//     or localStorage) to prevent XSS exfiltration and unnecessary re-renders.
//   - Refresh token lives in an httpOnly cookie — JS never sees it.
//   - On 401, the interceptor attempts a silent refresh via ``/auth/refresh``.
//     If it succeeds, the failed request is retried with the new token.
//     If it fails, the user is redirected to /login.

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

// ── Token storage (module-level closure) ─────────────────────────────────────
let accessToken: string | null = null;

/** Set the in-memory access token (called after login / refresh). */
export function setAccessToken(token: string | null): void {
	accessToken = token;
}

/** Get the current in-memory access token. */
export function getAccessToken(): string | null {
	return accessToken;
}

// ── Axios instance ───────────────────────────────────────────────────────────

const apiClient = axios.create({
	baseURL: import.meta.env.VITE_API_BASE_URL ?? "/", // Use Railway URL in prod; Vite proxy in dev
	withCredentials: true, // Send httpOnly cookies (refresh token)
	headers: { "Content-Type": "application/json" },
});

// ── Request interceptor: attach access token ─────────────────────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
	if (accessToken && config.headers) {
		config.headers.Authorization = `Bearer ${accessToken}`;
	}
	return config;
});

// Share one refresh request across session restoration and 401 retries.
let refreshPromise: Promise<string> | null = null;

export function refreshAccessToken(): Promise<string> {
	if (!refreshPromise) {
		refreshPromise = apiClient.post<{ access_token: string }>("/auth/refresh")
			.then(({ data }) => {
				setAccessToken(data.access_token);
				return data.access_token;
			})
			.finally(() => {
				refreshPromise = null;
			});
	}
	return refreshPromise;
}

// ── Response interceptor: auto-refresh on 401 ────────────────────────────────

apiClient.interceptors.response.use(
	(response) => response,
	async (error: AxiosError) => {
		const originalRequest = error.config as (InternalAxiosRequestConfig & {
			_retry?: boolean;
		}) | undefined;

		// Only attempt refresh on 401, if we haven't already retried, and the
		// failing request is NOT the /auth/refresh endpoint itself (avoids
		// infinite recursion when the refresh token is also expired).
		if (
			!originalRequest ||
			error.response?.status !== 401 ||
			originalRequest._retry ||
			originalRequest.url?.endsWith("/auth/refresh")
		) {
			return Promise.reject(error);
		}

		originalRequest._retry = true;

		let newToken: string;
		try {
			newToken = await refreshAccessToken();
		} catch (refreshError) {
			setAccessToken(null);
			// Redirect to login — use a dispatched event to avoid circular dependency
			window.dispatchEvent(new CustomEvent("auth:logout"));
			return Promise.reject(refreshError);
		}

		if (originalRequest.headers) {
			originalRequest.headers.Authorization = `Bearer ${newToken}`;
		}
		return apiClient(originalRequest);
	},
);

export default apiClient;
