import { api } from "./apiClient";
import type { CurrentUser, Token } from "../types/api";

export function login(username: string, password: string): Promise<Token> {
  return api.postForm<Token>("/api/v1/auth/login", { username, password });
}

export function fetchCurrentUser(token: string): Promise<CurrentUser> {
  return api.get<CurrentUser>("/api/v1/auth/me", token);
}
