import { describe, expect, it } from "vitest";
import type { Incident } from "../types/api";
import {
  canCancel, canResume, incidentClassLabel, incidentKind, incidentReasons, isAbortable, milestones, needsAttention, noticeText, statusExplanation,
} from "./incidentView";

const BASE = "2026-10-09T12:00:00Z";
const at = (seconds: number) => new Date(new Date(BASE).getTime() + seconds * 1000).toISOString();

function incident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: 7, print_job_id: 44, printer_id: 35, camera_id: 36, opened_at: at(30), reason: "would_pause", mode: "warn",
    defect_class: "spaghetti",
    streak: [
      { layer: 7, detection_id: 1, capture_id: 1, confidence: 0.81, captured_at: at(0) },
      { layer: 9, detection_id: 3, capture_id: 3, confidence: 0.92, captured_at: at(20) },
    ],
    detection_id: 3, first_defect_at: at(0), announced_at: at(30), pause_sent_at: null, paused_at: null, status: "open", outcome: null,
    decided_by: null, decided_at: null, label: "unlabeled", labeled_by: null, labeled_at: null, telemetry_snapshot: null, detail: null,
    updated_at: at(30), job_file_name: "cubo.gcode", seconds_to_pause: null,
    ...overrides,
  };
}

describe("what can be ordered", () => {
  it("resume only from a pause, cancel only while printing or paused, and only for administrators", () => {
    expect(canResume("paused", true)).toBe(true);
    expect(canResume("printing", true)).toBe(false);
    expect(canResume("error", true)).toBe(false); // Klipper in error: check the printer in person first
    expect(canResume("paused", false)).toBe(false);
    expect(canCancel("printing", true)).toBe(true);
    expect(canCancel("paused", true)).toBe(true);
    for (const status of ["idle", "error", "offline"] as const) expect(canCancel(status, true)).toBe(false);
    expect(canCancel("printing", false)).toBe(false);
  });

  it("the countdown can be aborted only before the pause is sent", () => {
    expect(isAbortable(incident({ reason: "auto_pause", mode: "on" }))).toBe(true);
    expect(isAbortable(incident({ reason: "auto_pause", mode: "on", pause_sent_at: at(45) }))).toBe(false);
    expect(isAbortable(incident({ reason: "would_pause" }))).toBe(false);
    expect(isAbortable(incident({ reason: "auto_pause", status: "closed" }))).toBe(false);
  });
});

describe("an incident that opened as a detection and was joined by the automatic pause", () => {
  const joined = (extra: Partial<Incident>) =>
    incident({
      reason: "detection", mode: "on",
      detail: { triggers: [{ reason: "detection", at: at(10) }, { reason: "auto_pause", at: at(30) }] },
      ...extra,
    });

  it("is judged by its strongest reason, not by the one it opened with", () => {
    expect(incidentReasons(joined({}))).toEqual(["detection", "auto_pause"]);
    expect(incidentKind(joined({}))).toBe("auto_pause");
    expect(incidentKind(incident({ reason: "detection", detail: { triggers: [{ reason: "detection" }, { reason: "would_pause" }] } }))).toBe("would_pause");
    expect(incidentKind(incident({ reason: "detection", detail: null }))).toBe("detection");
  });

  it("can be aborted while the countdown runs (this is what the on-mode demo showed missing)", () => {
    expect(isAbortable(joined({}))).toBe(true);
    expect(isAbortable(joined({ pause_sent_at: at(45) }))).toBe(false);
    expect(isAbortable(incident({ reason: "detection", mode: null, detail: { triggers: [{ reason: "detection" }] } }))).toBe(false);
    expect(statusExplanation(joined({}))).toContain("Cuenta regresiva");
    expect(noticeText(joined({}), "Creality Hi", "Spaghetti")).toContain("Pausa automática en Creality Hi");
  });
});

describe("where an incident stands", () => {
  it("says what is left to do in each state", () => {
    expect(statusExplanation(incident())).toContain("no se envió ninguna orden");
    expect(statusExplanation(incident({ reason: "auto_pause", mode: "on" }))).toContain("Cuenta regresiva");
    expect(statusExplanation(incident({ reason: "auto_pause", mode: "on", pause_sent_at: at(45) }))).toContain("esperando");
    expect(statusExplanation(incident({ status: "paused", paused_at: at(50) }))).toContain("Decide");
    expect(statusExplanation(incident({ status: "unconfirmed" }))).toContain("no confirmó");
    expect(statusExplanation(incident({ reason: "detection", mode: null }))).toContain("3 capas seguidas");
    expect(statusExplanation(incident({ status: "closed", outcome: "resumed", decided_by: "samuel (web)" }))).toBe("Se reanudó (samuel (web)).");
  });

  it("only a closed incident stops asking for attention", () => {
    expect(["open", "paused", "unconfirmed"].map((status) => needsAttention({ status } as Pick<Incident, "status">))).toEqual([true, true, true]);
    expect(needsAttention({ status: "closed" })).toBe(false);
  });

  it("the banner names the printer, the class and the last layer of the streak", () => {
    expect(noticeText(incident(), "Creality Hi", "Spaghetti")).toBe("Habría pausado (modo aviso) en Creality Hi: Spaghetti, capa 9");
    expect(noticeText(incident({ streak: [], reason: "pause" }), "Creality Hi", "Pausa")).toBe("La impresora se pausó en Creality Hi: Pausa");
  });

  it("a pause with no detection is shown as «Pausa»", () => {
    expect(incidentClassLabel("pausa", () => "x")).toBe("Pausa");
    expect(incidentClassLabel("spaghetti", (name) => name.toUpperCase())).toBe("SPAGHETTI");
  });
});

describe("milestones", () => {
  it("are ordered in time and measured from the first photo with the defect", () => {
    const steps = milestones(
      incident({ reason: "auto_pause", mode: "on", pause_sent_at: at(45), paused_at: at(47), status: "closed", outcome: "resumed", decided_by: "samuel", decided_at: at(300) }),
    );
    expect(steps.map((step) => [step.key, step.offsetS])).toEqual([
      ["first_defect", 0], ["opened", 30], ["announced", 30], ["pause_sent", 45], ["paused", 47], ["decided", 300],
    ]);
    expect(steps[steps.length - 1].label).toBe("Decisión: Se reanudó");
  });

  it("leave out what did not happen, and fall back to the opening time when the first photo is unknown", () => {
    const steps = milestones(incident({ first_defect_at: null, announced_at: null }));
    expect(steps.map((step) => step.key)).toEqual(["opened"]);
    expect(steps[0].offsetS).toBe(0);
  });
});
