import { api } from "./apiClient";
import type { CurrentUser, Token } from "../types/api";

export function login(username: string, password: string): Promise<Token> {
  return api.postForm<Token>("/api/v1/auth/login", { username, password });
}

/** A new token for a session that is still valid (the backend ends it 24 h after the login, however often it is renewed). */
export function refreshToken(token: string): Promise<Token> {
  return api.post<Token>("/api/v1/auth/refresh", undefined, token);
}

export function fetchCurrentUser(token: string): Promise<CurrentUser> {
  return api.get<CurrentUser>("/api/v1/auth/me", token);
}
