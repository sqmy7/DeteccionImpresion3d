// Single place that says how each model class is presented. The backend and the worker treat every class the
// same way (they just report what the model saw); which classes are trustworthy enough to count as a "defect" is a
// presentation decision, so it lives here.

export const DEFECT_CLASS_LABELS: Record<string, string> = {
  spaghetti: "Spaghetti",
  warping: "Warping",
  stringing: "Stringing",
  layer_shift: "Desplazamiento de capa",
  under_extrusion: "Sub-extrusión",
  blob_over_extrusion: "Exceso de material (blobs)",
};

// Informational classes are still shown, but marked as low-confidence and NOT counted as a reliable defect.
// blob_over_extrusion: on the 841-image test set its precision at the deployed threshold is ~0.47 per box /
// 0.56 per image (recall 0.15 per box), and no threshold reaches 90% precision - see
// inference/training/README.md, "Limitaciones conocidas". It also triggers no automatic alert.
export const INFORMATIONAL_CLASSES: Record<string, string> = {
  blob_over_extrusion:
    "Clase informativa: el modelo acierta menos de 6 de cada 10 veces con esta clase y no genera alertas automáticas.",
};

export function isInformationalClass(name: string): boolean {
  return name in INFORMATIONAL_CLASSES;
}

export function classLabel(name: string): string {
  return DEFECT_CLASS_LABELS[name] ?? name;
}

// Per-class color, from the Okabe-Ito palette (distinguishable with the common forms of color
// blindness); informational classes get a muted slate, not an alarming color. Color is never the
// only cue: maps and charts also show the class code below or its name.
const CLASS_COLORS: Record<string, string> = {
  spaghetti: "#D55E00", // vermillion
  warping: "#E69F00", // orange
  stringing: "#F0E442", // yellow
  layer_shift: "#CC79A7", // reddish purple
  under_extrusion: "#56B4E9", // sky blue
  blob_over_extrusion: "#94A3B8", // slate (informational)
};
const DEFAULT_CLASS_COLOR = "#94A3B8";

const CLASS_CODES: Record<string, string> = {
  spaghetti: "SP",
  warping: "WA",
  stringing: "ST",
  layer_shift: "LS",
  under_extrusion: "UE",
  blob_over_extrusion: "BL",
};

export function classColor(name: string): string {
  return CLASS_COLORS[name] ?? DEFAULT_CLASS_COLOR;
}

/** Two-letter code drawn on map markers, so classes are told apart without relying on color. */
export function classCode(name: string): string {
  return CLASS_CODES[name] ?? name.slice(0, 2).toUpperCase();
}

export type LayerStatus = "ok" | "info" | "defect";

export function getLayerStatus(hasDefect: boolean, defectClasses: string[]): LayerStatus {
  if (!hasDefect && defectClasses.length === 0) return "ok";
  // A flagged layer whose classes we can't see (older data) stays a defect: never downgrade what we can't explain.
  if (defectClasses.length === 0) return "defect";
  return defectClasses.some((c) => !isInformationalClass(c)) ? "defect" : "info";
}
