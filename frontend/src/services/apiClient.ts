export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function getWsUrl(token: string): string {
  const wsScheme = API_BASE_URL.startsWith("https") ? "wss" : "ws";
  const hostAndPath = API_BASE_URL.replace(/^https?:\/\//, "");
  return `${wsScheme}://${hostAndPath}/api/v1/ws?token=${encodeURIComponent(token)}`;
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
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body });

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
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
