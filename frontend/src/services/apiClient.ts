export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const SESSION_EXPIRED_MESSAGE = "Tu sesión caducó. Inicia sesión de nuevo.";

// The web renews the session token while it is open (context/AuthContext.tsx). Screens keep the token they were handed
// at login, so every request uses the newest one from here instead of the one the caller passes.
let activeToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setActiveToken(token: string | null): void {
  activeToken = token;
}

/** The newest token of the session, or `fallback` (the one the caller holds) if none has been renewed. */
export function freshToken(fallback: string): string {
  return activeToken ?? fallback;
}

/** Called when a request that carried the session token is answered 401: the session ended. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function getWsUrl(token: string): string {
  const wsScheme = API_BASE_URL.startsWith("https") ? "wss" : "ws";
  const hostAndPath = API_BASE_URL.replace(/^https?:\/\//, "");
  return `${wsScheme}://${hostAndPath}/api/v1/ws?token=${encodeURIComponent(freshToken(token))}`;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  token?: string | null;
  body?: unknown;
  form?: boolean;
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.body !== undefined) {
    if (options.form) {
      body = new URLSearchParams(options.body as Record<string, string>);
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else {
      body = JSON.stringify(options.body);
      headers["Content-Type"] = "application/json";
    }
  }

  if (options.token) {
    headers.Authorization = `Bearer ${freshToken(options.token)}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body });

  if (response.status === 401 && options.token) {
    // Not a wrong password (that is the login request, which carries no token): the session ended.
    onUnauthorized?.();
    throw new ApiError(401, SESSION_EXPIRED_MESSAGE);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") {
        detail = errorBody.detail;
      }
    } catch {
      // Response body wasn't JSON - keep the status text.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, token?: string | null) => request<T>("GET", path, { token }),
  post: <T>(path: string, body?: unknown, token?: string | null) => request<T>("POST", path, { body, token }),
  postForm: <T>(path: string, body: Record<string, string>, token?: string | null) =>
    request<T>("POST", path, { body, token, form: true }),
  patch: <T>(path: string, body?: unknown, token?: string | null) => request<T>("PATCH", path, { body, token }),
  put: <T>(path: string, body?: unknown, token?: string | null) => request<T>("PUT", path, { body, token }),
  del: (path: string, token?: string | null) => request<void>("DELETE", path, { token }),
};

/** Downloads an authenticated file (a PDF report) under the given name. */
export async function downloadFile(path: string, token: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Authorization: `Bearer ${freshToken(token)}` } });
  if (response.status === 401) {
    onUnauthorized?.();
    throw new ApiError(401, SESSION_EXPIRED_MESSAGE);
  }
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
