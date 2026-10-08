import { classLabel } from "../../config/defectClasses";
import { formatNumber } from "../../lib/format";
import type { FusionItem, FusionMethod, FusionOperator, FusionSignal } from "../../types/api";
import { EstimateNote } from "../ui";

const OPERATORS: Record<FusionOperator, string> = { ">": ">", ">=": "≥", "<=": "≤" };

function reading(signal: Pick<FusionSignal, "key" | "unit" | "operator" | "threshold"> & { value?: number | null }): string {
  if (signal.key === "no_filament") return signal.value == null ? "sin filamento" : signal.value >= 1 ? "sin filamento" : "con filamento";
  const digits = signal.unit === "s" || signal.unit === "%" ? 0 : 1;
  const threshold = `${OPERATORS[signal.operator]} ${formatNumber(signal.threshold, digits)} ${signal.unit}`.trim();
  return signal.value == null ? threshold : `${formatNumber(signal.value, digits)} ${signal.unit}; umbral ${threshold}`;
}

/** Under a detection: which telemetry readings raised its score, or why none did. */
export function FusionReasons({ item }: { item: FusionItem }) {
  const met = item.signals.filter((signal) => signal.met);
  let text: string;
  if (item.signals.length === 0) text = "Sin señales de telemetría para esta clase: el puntaje es el del modelo.";
  else if (item.window.samples === 0) text = "No hay telemetría de esa capa: el puntaje es el del modelo.";
  else if (met.length === 0) text = `La telemetría no muestra causas conocidas (${item.signals.length} señales revisadas).`;
  else text = `A favor: ${met.map((signal) => `${signal.label.toLowerCase()} (${reading(signal)})`).join("; ")}.`;
  return <p className={`text-xs ${met.length ? "text-warn-fg" : "text-faint"}`}>{text}</p>;
}

/** How the combined score is computed, with the thresholds and weights the backend uses. */
export function FusionMethodNote({ method }: { method: FusionMethod }) {
  return (
    <EstimateNote title="puntaje combinado de modelo y telemetría">
      <p>
        <span className="text-fg">Combinado = 1 − (1 − confianza del modelo) × ∏ (1 − peso de cada señal cumplida).</span> Las señales
        son lecturas de la impresora que explican ese tipo de defecto. La telemetría solo puede subir el puntaje: un atasco parcial o
        un filamento húmedo no dejan rastro en los sensores, así que una lectura normal no es evidencia en contra.
      </p>
      <p>{method.window}</p>
      <p>
        Pesos: fuerte {formatNumber(method.weights.fuerte, 2)}, media {formatNumber(method.weights.media, 2)}, débil{" "}
        {formatNumber(method.weights.debil, 2)}.{" "}
        {!method.calibrated && "Son pesos iniciales según qué tan directa es la relación física; no están calibrados con impresiones reales."}
      </p>
      <p className="text-fg">No cambia las alertas ni la pausa automática: siguen usando solo el modelo.</p>
      <ul className="flex flex-col gap-1.5">
        {method.signals.map((signal) => (
          <li key={signal.key}>
            <span className="text-fg">{signal.label}</span> ({reading(signal)}, peso {formatNumber(signal.weight, 2)}) —{" "}
            {signal.classes.map(classLabel).join(", ")}. {signal.rationale}
          </li>
        ))}
      </ul>
    </EstimateNote>
  );
}

export function fusionKey(detectionId: number | undefined, index: number | undefined): string {
  return `${detectionId}:${index}`;
}
