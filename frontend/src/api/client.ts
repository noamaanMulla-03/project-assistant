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
	baseURL: "/", // Vite proxy handles routing to backend
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

// ── Response interceptor: auto-refresh on 401 ────────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{
	resolve: (token: string) => void;
	reject: (error: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null): void {
	failedQueue.forEach((promise) => {
		if (error) {
			promise.reject(error);
		} else {
			promise.resolve(token!);
		}
	});
	failedQueue = [];
}

apiClient.interceptors.response.use(
	(response) => response,
	async (error: AxiosError) => {
		const originalRequest = error.config as InternalAxiosRequestConfig & {
			_retry?: boolean;
		};

		// Only attempt refresh on 401 and if we haven't already retried
		if (error.response?.status !== 401 || originalRequest._retry) {
			return Promise.reject(error);
		}

		// If a refresh is already in progress, queue this request
		if (isRefreshing) {
			return new Promise<string>((resolve, reject) => {
				failedQueue.push({ resolve, reject });
			})
				.then((token) => {
					if (originalRequest.headers) {
						originalRequest.headers.Authorization = `Bearer ${token}`;
					}
					return apiClient(originalRequest);
				})
				.catch((err) => Promise.reject(err));
		}

		originalRequest._retry = true;
		isRefreshing = true;

		try {
			const { data } = await axios.post(
				"/auth/refresh",
				{},
				{ withCredentials: true },
			);
			const newToken: string = data.access_token;
			setAccessToken(newToken);
			processQueue(null, newToken);

			if (originalRequest.headers) {
				originalRequest.headers.Authorization = `Bearer ${newToken}`;
			}
			return apiClient(originalRequest);
		} catch (refreshError) {
			processQueue(refreshError, null);
			setAccessToken(null);
			// Redirect to login — use a dispatched event to avoid circular dependency
			window.dispatchEvent(new CustomEvent("auth:logout"));
			return Promise.reject(refreshError);
		} finally {
			isRefreshing = false;
		}
	},
);

export default apiClient;
