import { describe, expect, it } from "vitest";
import { jobLayer, jobTime } from "./jobFacts";

const START = "2026-10-08T19:13:13Z";
const at = (seconds: number) => new Date(new Date(START).getTime() + seconds * 1000).toISOString();

describe("jobTime", () => {
  it("a late-joined finished job shows the printer's clock and says how long PrintWatch followed it", () => {
    // Job 43: PrintWatch followed 2 h 45 min of a 6 h 01 min print.
    const time = jobTime({ started_at: START, ended_at: at(9929), status: "completed", printed_s: 21660 });
    expect(time).toEqual({ seconds: 21660, source: "printer", note: "PrintWatch lo siguió 2 h 45 min" });
  });

  it("a job followed from the start shows the printer's clock without a note, even if heating makes the follow longer", () => {
    // Job 44: followed 3 min 36 s, printed 2 min 42 s by the printer's clock.
    const time = jobTime({ started_at: START, ended_at: at(216), status: "completed", printed_s: 162 });
    expect(time).toEqual({ seconds: 162, source: "printer", note: null });
  });

  it("an old job without the clock shows the time followed and claims nothing else", () => {
    const time = jobTime({ started_at: START, ended_at: at(3600), status: "completed", printed_s: null });
    expect(time).toEqual({ seconds: 3600, source: "followed", note: null });
  });

  it("a job from an API that predates the field is treated as unknown", () => {
    const time = jobTime({ started_at: START, ended_at: at(600), status: "failed" } as never);
    expect(time).toEqual({ seconds: 600, source: "followed", note: null });
  });

  it("a running job counts the time followed while it is followed from the start", () => {
    const nowMs = new Date(at(60)).getTime();
    const time = jobTime({ started_at: START, ended_at: null, status: "running", printed_s: null }, { liveRunningS: 8, nowMs });
    expect(time).toEqual({ seconds: 60, source: "followed", note: null });
  });

  it("a running job that PrintWatch joined late shows the live print clock", () => {
    const nowMs = new Date(at(600)).getTime();
    const time = jobTime({ started_at: START, ended_at: null, status: "running", printed_s: null }, { liveRunningS: 7200, nowMs });
    expect(time.seconds).toBe(7200);
    expect(time.source).toBe("printer");
    expect(time.note).toBe("PrintWatch lo siguió 10 min 00 s");
  });
});

describe("jobLayer", () => {
  it("shows the job's own last layer for a finished job even when the idle printer reports layer 0", () => {
    expect(jobLayer({ running: false, liveLayer: 0, summaryLayer: 486 })).toBe(486);
  });

  it("shows the live layer while the job is the one printing", () => {
    expect(jobLayer({ running: true, liveLayer: 12, summaryLayer: 11 })).toBe(12);
  });

  it("falls back to the job's layer when the live reading has none, and to nothing when neither exists", () => {
    expect(jobLayer({ running: true, liveLayer: null, summaryLayer: 11 })).toBe(11);
    expect(jobLayer({ running: false, liveLayer: 5, summaryLayer: null })).toBeNull();
  });
});
