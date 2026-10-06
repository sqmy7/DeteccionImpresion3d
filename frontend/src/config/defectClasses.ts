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

// Per-class color for bounding-box overlays (live view) - distinct, saturated hues per class so
// several boxes on screen stay distinguishable at a glance; informational classes get the same
// muted slate used for their "info" status elsewhere (LayerTimeline), not an alarming color.
const CLASS_COLORS: Record<string, string> = {
  spaghetti: "#ef4444", // red-500
  warping: "#f97316", // orange-500
  stringing: "#eab308", // yellow-500
  layer_shift: "#a855f7", // purple-500
  under_extrusion: "#ec4899", // pink-500
  blob_over_extrusion: "#64748b", // slate-500 (informational)
};
const DEFAULT_CLASS_COLOR = "#64748b"; // slate-500, for any class not in the palette above

export function classColor(name: string): string {
  return CLASS_COLORS[name] ?? DEFAULT_CLASS_COLOR;
}

export type LayerStatus = "ok" | "info" | "defect";

export function getLayerStatus(hasDefect: boolean, defectClasses: string[]): LayerStatus {
  if (!hasDefect && defectClasses.length === 0) return "ok";
  // A flagged layer whose classes we can't see (older data) stays a defect: never downgrade what we can't explain.
  if (defectClasses.length === 0) return "defect";
  return defectClasses.some((c) => !isInformationalClass(c)) ? "defect" : "info";
}
