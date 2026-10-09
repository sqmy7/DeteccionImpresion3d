import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, freshToken, SESSION_EXPIRED_MESSAGE, setActiveToken, setUnauthorizedHandler } from "./apiClient";

function respond(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}

beforeEach(() => {
  setActiveToken(null);
  setUnauthorizedHandler(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("a 401 on a request that carried the session token", () => {
  it("tells the session handler and says the session expired, not the server's English text", async () => {
    respond(401, { detail: "Could not validate credentials" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    const error = await api.get("/api/v1/printers", "token-viejo").catch((reason: unknown) => reason);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).message).toBe(SESSION_EXPIRED_MESSAGE);
  });

  it("does not fire for the login request: wrong password is not an expired session", async () => {
    respond(401, { detail: "Incorrect username or password" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    const error = await api.postForm("/api/v1/auth/login", { username: "a", password: "b" }).catch((reason: unknown) => reason);

    expect(handler).not.toHaveBeenCalled();
    expect((error as ApiError).message).toBe("Incorrect username or password");
  });

  it("does not fire for other errors", async () => {
    respond(409, { detail: "Ya hay una orden en curso" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await api.post("/api/v1/printers/1/resume", undefined, "token").catch(() => undefined);

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("the renewed token", () => {
  it("is the one sent, even to callers that still hold the token they were given at login", async () => {
    respond(200, {});
    setActiveToken("token-renovado");

    await api.get("/api/v1/printers", "token-del-login");

    const init = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-renovado");
  });

  it("freshToken falls back to the given one until a renewal arrives", () => {
    expect(freshToken("token-del-login")).toBe("token-del-login");
    setActiveToken("token-renovado");
    expect(freshToken("token-del-login")).toBe("token-renovado");
  });
});
