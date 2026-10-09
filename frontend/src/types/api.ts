export type PrinterStatus = "idle" | "printing" | "paused" | "error" | "offline";

export interface Printer {
  id: number;
  name: string;
  model: string | null;
  octoprint_url: string;
  integration_type: "octoprint" | "moonraker";
  last_known_status: PrinterStatus;
  created_at: string;
  updated_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export type UserRole = "admin" | "viewer";

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  created_at: string;
}

export type CameraSourceType = "usb" | "rtsp" | "mjpeg_http";
export type CameraRole = "primary" | "secondary";

export interface Camera {
  id: number;
  printer_id: number;
  name: string;
  source_type: CameraSourceType;
  source_uri: string;
  role: CameraRole;
  roi: Record<string, number> | null;
  is_active: boolean;
  created_at: string;
}

export type JobStatus = "running" | "completed" | "failed" | "cancelled";

export interface PrintJob {
  id: number;
  printer_id: number;
  octoprint_job_id: string | null;
  file_name: string;
  status: JobStatus;
  estimated_layers: number | null;
  started_at: string;
  ended_at: string | null;
  /** Seconds the job printed by the printer's own clock; null for jobs recorded before it was kept. */
  printed_s: number | null;
}

export interface TimelineEntry {
  layer_number: number;
  z_height: string | null; // Decimal -> JSON string (Pydantic default), e.g. "65.40"
  capture_id: number | null;
  has_defect: boolean;
  defect_classes: string[];
  thumbnail_url: string | null;
}

export interface ModelVersionSummary {
  id: number;
  name: string;
}

export interface JobSummary {
  job_id: number;
  current_layer: number | null;
  total_layers_recorded: number;
  layers_captured: number;
  layers_ok: number;
  layers_with_defect: number;
  defect_class_counts: Record<string, number>;
  active_alerts_count: number;
  latest_model_version: ModelVersionSummary | null;
}

export interface LayerCapture {
  id: number;
  layer_id: number;
  camera_id: number;
  image_path: string;
  dominant_color_rgb: string | null;
  captured_at: string;
}

export interface DetectionBoxDetail {
  class: string;
  confidence: number;
  box: [number, number, number, number];
}

export interface Detection {
  id: number;
  capture_id: number;
  model_version_id: number;
  has_defect: boolean;
  max_confidence: string | null; // Decimal -> JSON string
  defect_classes: string[];
  raw_output: { detections: DetectionBoxDetail[] };
  created_at: string;
}

export type AlertSeverity = "warning" | "critical";
export type AlertStatus = "new" | "acknowledged" | "dismissed" | "false_positive";

export interface Alert {
  id: number;
  detection_id: number;
  printer_id: number;
  severity: AlertSeverity;
  status: AlertStatus;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
  created_at: string;
}

export interface AlertListItem {
  id: number;
  detection_id: number;
  printer_id: number;
  printer_name: string;
  severity: AlertSeverity;
  status: AlertStatus;
  acknowledged_by: number | null;
  acknowledged_at: string | null;
  created_at: string;
  print_job_id: number | null;
  layer_number: number | null;
  file_name: string | null;
}

// --- Telemetry (backend Fase 1) ---

export type ExtraSensors = Record<string, number | boolean>;

export interface TelemetryValues {
  layer_number: number | null;
  x: number | null;
  y: number | null;
  z: number | null;
  velocity: number | null;
  extruder_velocity: number | null;
  extruder_temp: number | null;
  extruder_target: number | null;
  extruder_power: number | null;
  bed_temp: number | null;
  bed_target: number | null;
  bed_power: number | null;
  fan_speed: number | null;
  speed_factor: number | null;
  extrude_factor: number | null;
  z_offset: number | null;
  progress: number | null;
  filament_used: number | null;
  extra: ExtraSensors | null;
}

export interface TelemetryPoint extends TelemetryValues {
  ts: string;
}

export interface JobTelemetry {
  job_id: number;
  samples: number;
  bucket_seconds: number | null;
  points: TelemetryPoint[];
}

/** What the listener pushes once per second (telemetry.sample) and /telemetry/latest returns. */
export interface TelemetryReading extends TelemetryValues {
  printer_id: number;
  job_id: number | null;
  state: string | null;
  ts: string;
}

export interface Layer {
  id: number;
  job_id: number;
  layer_number: number;
  z_height: string;
  detected_at: string;
  telemetry: (Partial<TelemetryValues> & { current_object?: string }) | null;
}

// --- Event log (backend Fases 1 y 2) ---

export type EventOrigin = "printwatch" | "console" | "gcode_file" | "printer" | "external" | "monitor";

export interface PrinterEvent {
  id: number;
  printer_id: number;
  print_job_id: number | null;
  ts: string;
  klipper_eventtime: number | null;
  event_type: string;
  field: string | null;
  value_before: unknown;
  value_after: unknown;
  origin: EventOrigin;
  detail: Record<string, unknown> | null;
  hash: string;
}

export interface ChainVerification {
  ok: boolean;
  events_checked: number;
  first_broken_id: number | null;
  reason: "prev_hash_mismatch" | "content_changed" | null;
  last_hash: string | null;
}

// --- Bed map (backend Fase 3) ---

export interface BedObject {
  name: string;
  center?: [number, number];
  polygon?: [number, number][];
}

export interface BedMesh {
  profile_name: string | null;
  mesh_min: [number, number];
  mesh_max: [number, number];
  probed_matrix: number[][];
}

export interface BedGeometry {
  axis_minimum: number[] | null;
  axis_maximum: number[] | null;
  bed_mesh: BedMesh | null;
  objects: BedObject[];
  // What the slicer wrote about the file (Moonraker's metadata); only in newer jobs.
  file?: {
    estimated_time?: number;
    estimated_time_source?: "filename";
    filament_total?: number;
    filament_weight_total?: number;
    filament_type?: string;
    slicer?: string;
  } | null;
}

export interface CameraCalibration {
  id: number;
  camera_id: number;
  created_at: string;
  created_by: number | null;
  image_points: [number, number][];
  bed_points: [number, number][];
  image_width: number;
  image_height: number;
  bed_moves_in_image: boolean;
  reference_y: number | null;
  focal_px: number | null;
  camera_position: [number, number, number] | null;
  warnings: string[];
  /** Information that is not a problem (a fixed focal, or one far from the C922's: another camera has another field of view). */
  notes: string[];
  /** "estimated" from the marks, "assumed" (C922 field of view) or "fixed" (given by the user). */
  focal_source: "estimated" | "assumed" | "fixed" | null;
  typical_focal_px: number | null;
  /** Per mark, in order: how far the camera model puts that corner from where it was marked. */
  marks: MarkError[] | null;
  /** The same with the camera's known focal, when the focal in use is another one. */
  marks_at_typical_focal: MarkError[] | null;
}

export interface MarkError {
  error_px: number;
  error_mm: number;
}

export interface CalibrationCreate {
  image_points: [number, number][];
  bed_points?: [number, number][];
  image_width: number;
  image_height: number;
  bed_moves_in_image: boolean;
  reference_y?: number | null;
  /** The camera's known focal length in pixels, used as is instead of estimating it. */
  focal_px?: number | null;
}

export interface LocatedDefect {
  detection_id: number;
  capture_id: number;
  camera_id: number;
  calibration_id: number;
  calibration_after_capture: boolean;
  layer_number: number;
  z: number;
  class_name: string | null;
  confidence: number | null;
  box: number[];
  x: number;
  y: number;
  uncertainty_mm: number;
  reliable: boolean;
  parallax_mm: number;
  shift_mm: number;
  object: string | null;
  head: { x: number | null; y: number | null; z: number | null };
  current_object: string | null;
}

export interface JobBedMap {
  job_id: number;
  geometry: BedGeometry | null;
  calibrated_cameras: number[];
  defects: LocatedDefect[];
  skipped_boxes: number;
  head_path: [number, number][];
}

// --- Analytics ---

export interface JobAnalytics {
  id: number;
  printer_id: number;
  file_name: string;
  status: JobStatus;
  started_at: string;
  ended_at: string | null;
  duration_s: number;
  layers: number;
  layers_with_defect: number;
  defect_rate: number | null;
  classes: Record<string, number>;
  interventions: Record<string, number>;
  telemetry_samples: number;
  nozzle_error_mean_c: number | null;
  nozzle_error_max_c: number | null;
  bed_error_mean_c: number | null;
  filament_m: number | null;
  cost?: number | null; // estimate: filament + heater energy
}

export interface AnalyticsSummary {
  totals: {
    jobs: number;
    success_rate?: number | null;
    print_hours?: number | null;
    layers?: number | null;
    layers_with_defect?: number | null;
    defect_rate?: number | null;
    interventions?: number | null;
    filament_m?: number | null;
    cost?: number | null;
  };
  status_counts: Record<string, number>;
  defects_by_class: Record<string, number>;
  interventions_by_origin: Record<string, number>;
  jobs: JobAnalytics[];
  currency?: string | null;
  cost_settings_are_default?: boolean | null;
}

export interface BedHeatmap {
  printer_id: number;
  cell_mm: number;
  width_mm: number;
  depth_mm: number;
  counts: number[][];
  jobs: number;
  located: number;
  unreliable: number;
  skipped_boxes: number;
  bed_mesh: BedMesh | null;
}

// --- Combined score: model + telemetry (Fase 5) ---

export type FusionOperator = ">" | ">=" | "<=";

export interface FusionSignal {
  key: string;
  label: string;
  unit: string;
  operator: FusionOperator;
  threshold: number;
  weight: number;
  value: number | null; // null: no data for it in the window
  met: boolean;
}

export interface FusionItem {
  detection_id: number;
  box_index: number;
  layer_number: number;
  class_name: string | null;
  confidence: number | null;
  score: number;
  signals: FusionSignal[];
  window: { source: "telemetry" | "layer_snapshot" | null; samples: number; layers: number[] };
}

export interface FusionMethodSignal {
  key: string;
  label: string;
  unit: string;
  operator: FusionOperator;
  threshold: number;
  weight: number;
  rationale: string;
  classes: string[];
}

export interface FusionMethod {
  formula: string;
  window: string;
  weights: Record<string, number>;
  calibrated: boolean;
  signals: FusionMethodSignal[];
}

export interface JobFusion {
  job_id: number;
  items: FusionItem[];
  method: FusionMethod;
}

// --- Printer health (Fase 5) ---

export type HealthStatus = "normal" | "attention" | "insufficient";

export interface HealthPoint {
  job_id: number;
  started_at: string;
  file_name: string;
  value: number;
  target: number | null;
  flags: string[];
}

export interface HealthMetric {
  key: "hold_power" | "oscillation" | "max_excursion" | "heating_rate";
  label: string;
  unit: string;
  worse: "up" | "down";
  status: HealthStatus;
  baseline: { n: number; mean: number; std: number; upper: number; lower: number } | null;
  findings: string[];
  points: HealthPoint[];
}

export interface HealthHeater {
  heater: "extruder" | "bed";
  label: string;
  target_bucket: number | null;
  metrics: HealthMetric[];
}

export interface HealthMethod {
  settle_delta_c: number;
  in_range_c: number;
  min_steady_samples: number;
  min_heatup_c: number;
  target_bucket_c: number;
  min_baseline_jobs: number;
  max_baseline_jobs: number;
  metrics: { key: string; label: string; unit: string; worse: string; description: string }[];
}

export interface PrinterHealth {
  printer_id: number;
  jobs_considered: number;
  jobs_with_telemetry: number;
  heaters: HealthHeater[];
  method: HealthMethod;
}
// --- Cost estimate (Fase 5) ---

export interface CostSettings {
  currency: string;
  filament_price_per_kg: number;
  energy_price_per_kwh: number;
  extruder_heater_w: number;
  bed_heater_w: number;
  filament_diameter_mm: number;
  default_density_g_cm3: number;
}

export interface CostSettingsRead extends CostSettings {
  is_default: boolean;
  updated_at: string | null;
}

export interface JobCost {
  job_id: number;
  currency: string;
  filament: {
    used_mm: number | null;
    used_g: number | null;
    method: "slicer" | "density" | null;
    density: number | null;
    material: string | null;
    cost: number | null;
    estimated_mm: number | null;
    estimated_g: number | null;
  };
  energy: { extruder_wh: number; bed_wh: number; total_kwh: number; covered_seconds: number; cost: number } | null;
  total_cost: number | null;
  settings: CostSettings;
  settings_are_default: boolean;
}