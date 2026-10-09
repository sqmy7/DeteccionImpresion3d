import { describe, expect, it } from "vitest";
import { feedState, STALE_FRAME_SECONDS } from "./feedState";

describe("feedState", () => {
  it("is loading until the first picture or the first failure", () => {
    expect(feedState(null, false)).toBe("loading");
    expect(feedState(null, true)).toBe("error");
  });

  it("a recent frame is live and an old one is stale (the camera stopped)", () => {
    expect(feedState({ ageSeconds: 1.2 }, false)).toBe("live");
    expect(feedState({ ageSeconds: STALE_FRAME_SECONDS }, false)).toBe("live");
    expect(feedState({ ageSeconds: STALE_FRAME_SECONDS + 0.1 }, false)).toBe("stale");
    expect(feedState({ ageSeconds: 3 * 3600 }, false)).toBe("stale");
  });

  it("a frame without an age is trusted, and a failure after a good frame is an error", () => {
    expect(feedState({ ageSeconds: null }, false)).toBe("live");
    expect(feedState({ ageSeconds: 1 }, true)).toBe("error");
  });
});
