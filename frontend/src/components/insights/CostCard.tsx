import { Coins, Settings2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../../hooks/useAuth";
import { formatMoney, formatNumber } from "../../lib/format";
import { saveCostSettings } from "../../services/insights";
import type { CostSettings, JobCost } from "../../types/api";
import { Button, Card, ErrorNote, EstimateNote } from "../ui";

const FIELDS: { key: keyof CostSettings; label: string; step: string; hint: string }[] = [
  { key: "filament_price_per_kg", label: "Filamento, precio por kg", step: "100", hint: "" },
  { key: "energy_price_per_kwh", label: "Energía, precio por kWh", step: "1", hint: "Tarifa de la factura de energía" },
  { key: "extruder_heater_w", label: "Calentador de la boquilla (W)", step: "1", hint: "Hi: 50 W" },
  { key: "bed_heater_w", label: "Calentador de la cama (W)", step: "1", hint: "Hi: 1000 W a 220 V, ~300 W a 120 V" },
  { key: "filament_diameter_mm", label: "Diámetro del filamento (mm)", step: "0.01", hint: "" },
  { key: "default_density_g_cm3", label: "Densidad si el archivo no dice el material (g/cm³)", step: "0.01", hint: "PLA: 1,24" },
];

function SettingsForm({ initial, onSaved, onCancel }: { initial: CostSettings; onSaved: () => void; onCancel: () => void }) {
  const { token } = useAuth();
  const [values, setValues] = useState<CostSettings>(initial);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      await saveCostSettings(token, values);
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-lg border border-line bg-surface-2/40 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Moneda
          <input
            value={values.currency}
            maxLength={8}
            onChange={(event) => setValues({ ...values, currency: event.target.value.toUpperCase() })}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-fg"
          />
        </label>
        {FIELDS.map((field) => (
          <label key={field.key} className="flex flex-col gap-1 text-xs text-muted">
            {field.label}
            <input
              type="number"
              min={0}
              step={field.step}
              value={values[field.key] as number}
              onChange={(event) => setValues({ ...values, [field.key]: Number(event.target.value) })}
              className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm tabular text-fg"
            />
            {field.hint && <span className="text-faint">{field.hint}</span>}
          </label>
        ))}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={saving}>
          Guardar
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
      <p className="text-xs text-faint">Aplica a todos los trabajos (también a los anteriores) y a sus reportes.</p>
    </form>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="text-right tabular text-fg">{children}</dd>
    </>
  );
}

/** Filament and heater energy of a job at the configured prices, clearly marked as an estimate. */
export function JobCostCard({ cost, onChanged }: { cost: JobCost; onChanged: () => void }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const { filament, energy, currency, settings } = cost;

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Coins size={15} className="text-faint" />
          Costo estimado
        </span>
      }
      subtitle="Filamento usado y energía de los calentadores, a los precios configurados"
      actions={
        user?.role === "admin" && (
          <Button size="sm" variant="ghost" icon={<Settings2 size={14} />} onClick={() => setEditing((value) => !value)}>
            Precios y potencias
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-3">
        {cost.settings_are_default && (
          <p className="text-xs text-warn-fg">Los precios son valores de ejemplo: todavía nadie los configuró.</p>
        )}
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
          <Row label="Filamento">
            {filament.used_g == null ? (
              "sin telemetría"
            ) : (
              <>
                {formatNumber(filament.used_g, 1)} g ({formatNumber((filament.used_mm ?? 0) / 1000, 2)} m) · {formatMoney(filament.cost, currency)}
              </>
            )}
          </Row>
          <Row label="Energía de calentadores">
            {energy ? (
              <>
                {formatNumber(energy.total_kwh, 3)} kWh · {formatMoney(energy.cost, currency)}
              </>
            ) : (
              "sin telemetría"
            )}
          </Row>
          <Row label="Total">
            <span className="font-semibold">{formatMoney(cost.total_cost, currency)}</span>
          </Row>
          {(filament.estimated_mm || filament.estimated_g) && (
            <Row label="Laminador (archivo completo)">
              {filament.estimated_g ? `${formatNumber(filament.estimated_g, 1)} g · ` : ""}
              {filament.estimated_mm ? `${formatNumber(filament.estimated_mm / 1000, 2)} m` : ""}
            </Row>
          )}
        </dl>

        {editing && (
          <SettingsForm
            initial={settings}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              onChanged();
            }}
          />
        )}

        <EstimateNote title="costo: cómo se calcula">
          <p>
            <span className="text-fg">Filamento:</span> lo que la impresora mandó extruir (print_stats.filament_used), no un pesaje: no
            cuenta purgas fuera del archivo ni el filamento que quede en la boquilla.{" "}
            {filament.method === "slicer"
              ? "Los gramos salen de los gramos por milímetro que calculó el laminador para este archivo."
              : `Los gramos salen de la densidad ${filament.material ? `típica del ${filament.material}` : "por defecto"} (${formatNumber(
                  filament.density,
                  2,
                )} g/cm³) y un diámetro de ${formatNumber(settings.filament_diameter_mm, 2)} mm.`}{" "}
            Precio: {formatMoney(settings.filament_price_per_kg, currency)} por kg.
          </p>
          <p>
            <span className="text-fg">Energía:</span> solo los dos calentadores, como su PWM en cada segundo por su potencia nominal (boquilla{" "}
            {formatNumber(settings.extruder_heater_w, 0)} W, cama {formatNumber(settings.bed_heater_w, 0)} W). No incluye motores,
            ventiladores, electrónica ni pantalla, ni los huecos de más de 5 s en la telemetría. La cama de la Hi es de 1000 W a 220 V; un
            calentador resistivo rinde con el cuadrado del voltaje, así que a 120 V da ~300 W (coherente con los 390 W nominales de la
            impresora a 110 V). Precio: {formatMoney(settings.energy_price_per_kwh, currency)} por kWh.
          </p>
        </EstimateNote>
      </div>
    </Card>
  );
}
