import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CHECK_EVERY_MS, shouldRenew } from "../lib/session";
import { freshToken, setActiveToken, setUnauthorizedHandler } from "../services/apiClient";
import { fetchCurrentUser, login as loginRequest, refreshToken } from "../services/auth";
import type { CurrentUser } from "../types/api";

const TOKEN_STORAGE_KEY = "printwatch.token";

interface AuthContextValue {
  token: string | null;
  user: CurrentUser | null;
  isLoading: boolean;
  /** The session ended on its own (token expired or refused): the login screen says so. */
  sessionExpired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  // A request that carried the session token and got a 401: the session is over. Go back to the login with a
  // message instead of leaving every screen showing "Unauthorized".
  const expire = useCallback(() => {
    if (!tokenRef.current) return; // already logged out: a late answer is not an expired session
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setActiveToken(null);
    setToken(null);
    setUser(null);
    setSessionExpired(true);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(expire);
    return () => setUnauthorizedHandler(null);
  }, [expire]);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    fetchCurrentUser(token)
      .then((fetchedUser) => {
        if (!cancelled) setUser(fetchedUser);
      })
      .catch(() => {
        // Stored token is invalid/expired - drop it and fall back to the login screen. (A 401 already went through
        // `expire`, which also says the session expired; other failures just end here.)
        if (!cancelled) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          setActiveToken(null);
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  // Keeps the session alive while the web is open: a print lasts hours and the token one hour. The renewed token goes
  // to the request layer (apiClient.freshToken) and to storage; `token` here stays the one of the login so no screen
  // reloads or reconnects when it is renewed.
  useEffect(() => {
    if (!token) return;
    setActiveToken(token);
    let stopped = false;
    const renew = async () => {
      const current = freshToken(token);
      if (!shouldRenew(current, Date.now())) return;
      try {
        const renewed = await refreshToken(current);
        if (stopped) return;
        setActiveToken(renewed.access_token);
        localStorage.setItem(TOKEN_STORAGE_KEY, renewed.access_token);
      } catch {
        // A 401 ended the session through `expire`; anything else is tried again at the next check.
      }
    };
    void renew();
    const timer = window.setInterval(() => void renew(), CHECK_EVERY_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void renew();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [token]);

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginRequest(username, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
    setActiveToken(result.access_token);
    setSessionExpired(false);
    setToken(result.access_token);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setActiveToken(null);
    setSessionExpired(false);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ token, user, isLoading, sessionExpired, login, logout }),
    [token, user, isLoading, sessionExpired, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
