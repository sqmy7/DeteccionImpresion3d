import { describe, expect, it } from "vitest";
import { RENEW_WINDOW_MS, shouldRenew, tokenExpiresAt } from "./session";

function token(payload: Record<string, unknown>): string {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(payload)}.firma`;
}

const NOW = 1_800_000_000_000;

describe("tokenExpiresAt", () => {
  it("reads exp (seconds) as milliseconds", () => {
    expect(tokenExpiresAt(token({ sub: "1", exp: NOW / 1000 + 600 }))).toBe(NOW + 600_000);
  });

  it("returns null when the token cannot be read", () => {
    expect(tokenExpiresAt("no-es-un-token")).toBeNull();
    expect(tokenExpiresAt("a.%%%.c")).toBeNull();
    expect(tokenExpiresAt(token({ sub: "1" }))).toBeNull();
  });
});

describe("shouldRenew", () => {
  it("does not renew a token with plenty of time left", () => {
    expect(shouldRenew(token({ exp: (NOW + 50 * 60_000) / 1000 }), NOW)).toBe(false);
  });

  it("renews one with less than the window left", () => {
    expect(shouldRenew(token({ exp: (NOW + RENEW_WINDOW_MS - 1000) / 1000 }), NOW)).toBe(true);
    expect(shouldRenew(token({ exp: (NOW + 60_000) / 1000 }), NOW)).toBe(true);
  });

  it("does not try to renew one that already expired: the server would refuse it", () => {
    expect(shouldRenew(token({ exp: (NOW - 1000) / 1000 }), NOW)).toBe(false);
  });

  it("does nothing with a token it cannot read", () => {
    expect(shouldRenew("basura", NOW)).toBe(false);
  });
});
