import { describe, expect, it } from "vitest";
import { CANCEL_WORD, isCancelConfirmed } from "./cancelConfirm";

describe("isCancelConfirmed", () => {
  it("accepts only the exact word", () => {
    expect(CANCEL_WORD).toBe("CANCELAR");
    expect(isCancelConfirmed("CANCELAR")).toBe(true);
    expect(isCancelConfirmed("  CANCELAR  ")).toBe(true); // stray spaces around it are forgiven
  });

  it("refuses anything else", () => {
    for (const typed of ["", "cancelar", "Cancelar", "CANCELA", "CANCELAR ya", "SI", "CANCEL", "CANCELAR​"]) {
      expect(isCancelConfirmed(typed)).toBe(false);
    }
  });
});
