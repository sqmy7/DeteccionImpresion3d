import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchCurrentUser, login as loginRequest } from "../services/auth";
import type { CurrentUser } from "../types/api";

const TOKEN_STORAGE_KEY = "printwatch.token";

interface AuthContextValue {
  token: string | null;
  user: CurrentUser | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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
        // Stored token is invalid/expired - drop it and fall back to the login screen.
        if (!cancelled) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
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

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginRequest(username, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
    setToken(result.access_token);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ token, user, isLoading, login, logout }),
    [token, user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
