export type PrinterStatus = "idle" | "printing" | "paused" | "error" | "offline";

export interface Printer {
  id: number;
  name: string;
  model: string | null;
  octoprint_url: string;
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
}
