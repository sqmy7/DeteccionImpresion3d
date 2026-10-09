import { describe, expect, it } from "vitest";
import { actionPhase, CONFIRM_TIMEOUT_MS, progressLabel, timeoutNote, type PendingPrintAction } from "./printAction";

const resume: PendingPrintAction = { kind: "resume", from: "paused", startedAt: 1_000_000 };

describe("actionPhase", () => {
  it("waits while the printer is still in the state it was in when the button was pressed", () => {
    expect(actionPhase(resume, "paused", resume.startedAt + 30_000)).toBe("waiting");
  });

  it("is done as soon as the state changes, however long the request took", () => {
    expect(actionPhase(resume, "printing", resume.startedAt + 64_000)).toBe("done");
  });

  it("is done when the state already changed before the answer arrived (a pause shows within a second)", () => {
    const pause: PendingPrintAction = { kind: "pause", from: "printing", startedAt: 5_000 };
    expect(actionPhase(pause, "paused", 5_000)).toBe("done");
  });

  it("counts any other state as a change, an error included, so the web stops saying 'Reanudando'", () => {
    expect(actionPhase(resume, "error", resume.startedAt + 3_000)).toBe("done");
  });

  it("says so when the state did not change in the waiting time, and not before", () => {
    expect(actionPhase(resume, "paused", resume.startedAt + CONFIRM_TIMEOUT_MS - 1)).toBe("waiting");
    expect(actionPhase(resume, "paused", resume.startedAt + CONFIRM_TIMEOUT_MS)).toBe("timeout");
  });

  it("a change wins over the timeout", () => {
    expect(actionPhase(resume, "printing", resume.startedAt + CONFIRM_TIMEOUT_MS + 5_000)).toBe("done");
  });

  it("keeps waiting when the printer's state is not known yet", () => {
    expect(actionPhase(resume, undefined, resume.startedAt + 10_000)).toBe("waiting");
    expect(actionPhase({ ...resume, from: undefined }, "printing", resume.startedAt + 10_000)).toBe("waiting");
  });
});

describe("texts", () => {
  it("shows the action in progress with the seconds", () => {
    expect(progressLabel("resume", 23.7)).toBe("Reanudando… 23 s");
    expect(progressLabel("pause", -1)).toBe("Pausando… 0 s");
    expect(progressLabel("cancel", 5)).toBe("Cancelando… 5 s");
  });

  it("the timeout note says the order was sent and the state did not change, not that it failed", () => {
    expect(timeoutNote("resume")).toContain("se envió");
    expect(timeoutNote("resume")).toContain("reanudar");
    expect(timeoutNote("resume")).not.toMatch(/error|falló/i);
  });
});
