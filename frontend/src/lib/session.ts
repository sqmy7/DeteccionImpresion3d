/** The session token lives one hour. While the web is open it is renewed (POST /auth/refresh) when less than this is
 * left, checked every CHECK_EVERY_MS and whenever the tab comes back to the front, so a print that lasts hours does
 * not end with the session expiring in the middle of it. The backend ends a session after jwt_max_session_hours
 * (24 h) from the login however often it is renewed. */
export const RENEW_WINDOW_MS = 30 * 60 * 1000;
export const CHECK_EVERY_MS = 5 * 60 * 1000;

/** When the token expires (ms since the epoch), read from its payload; null if it cannot be read. The signature is
 * not checked: only the server does that. This is just for deciding when to renew. */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** True when the token is still valid but has less than RENEW_WINDOW_MS left. An expired one cannot be renewed: the
 * next request gets a 401 and the web asks for the password again. */
export function shouldRenew(token: string, now: number): boolean {
  const expiresAt = tokenExpiresAt(token);
  if (expiresAt === null) return false;
  const left = expiresAt - now;
  return left > 0 && left < RENEW_WINDOW_MS;
}
