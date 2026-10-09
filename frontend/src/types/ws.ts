import type { PrinterEvent, PrinterStatus, TelemetryReading } from "./api";

// Event types from the WS contract: printer.status, layer.captured, detection.result,
// detection.boxes, detection.alert, job.started/completed/failed/cancelled,
// auto_pause.pending/aborted/executed/failed, telemetry.sample (1 Hz per connected printer)
// and printer.event (each new event-log entry).
export type WsEventType =
  | "printer.status"
  | "layer.captured"
  | "detection.result"
  | "detection.boxes"
  | "detection.alert"
  | "job.started"
  | "job.completed"
  | "job.failed"
  | "job.cancelled"
  | "auto_pause.pending"
  | "auto_pause.aborted"
  | "auto_pause.executed"
  | "auto_pause.failed"
  | "auto_pause.would_pause"
  | "auto_pause.confirmed"
  | "auto_pause.not_confirmed"
  | "incident.opened"
  | "incident.updated"
  | "telemetry.sample"
  | "printer.event";

export type TelemetrySampleEvent = TelemetryReading;
export type PrinterEventEvent = PrinterEvent;

export interface WsEnvelope<T = unknown> {
  type: WsEventType;
  timestamp: string;
  data: T;
}

export interface PrinterStatusEvent {
  printer_id: number;
  status: PrinterStatus;
}

export interface LayerCapturedEvent {
  capture_id: number;
  printer_id: number;
  job_id: number;
  layer_id: number;
  layer_number: number;
  camera_id: number;
  image_path: string;
}

export interface DetectionResultEvent {
  detection_id: number;
  capture_id: number;
  printer_id: number;
  job_id: number;
  layer_number: number;
  camera_id: number;
  has_defect: boolean;
  max_confidence: number | null;
  defect_classes: string[];
}

// Coordinates: normalized 0..1 against the FULL captured frame (the same image VideoFeed
// shows) - already adjusted server-side for any camera ROI crop, see inference/main.py.
export interface DetectionBox {
  class: string;
  confidence: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface DetectionBoxesEvent {
  detection_id: number;
  capture_id: number;
  printer_id: number;
  job_id: number;
  layer_number: number;
  camera_id: number;
  boxes: DetectionBox[];
}

export interface DetectionAlertEvent {
  alert_id: number;
  printer_id: number;
  detection_id: number;
  severity: "warning" | "critical";
  status: "new" | "acknowledged" | "dismissed" | "false_positive";
  acknowledged_by: number | null;
}

export interface JobStartedEvent {
  job_id: number;
  printer_id: number;
  file_name: string;
  estimated_layers: number | null;
  started_at: string;
}

export interface JobEndedEvent {
  job_id: number;
  printer_id: number;
  status: "completed" | "failed" | "cancelled";
  ended_at: string;
}

export interface AutoPausePendingEvent {
  job_id: number;
  printer_id: number;
  reason: string;
  consecutive_layers: number;
  executes_at: string; // ISO timestamp - compute the countdown from this, not a local timer
  incident_id?: number | null;
}

export interface AutoPauseAbortedEvent {
  job_id: number;
}

/** The pause order went out; whether Klipper paused is told by auto_pause.confirmed or auto_pause.not_confirmed. */
export interface AutoPauseExecutedEvent {
  job_id: number;
  printer_id: number;
  reason: string;
  incident_id?: number | null;
}

export interface AutoPauseConfirmedEvent {
  job_id: number;
  printer_id: number;
  incident_id?: number | null;
  seconds: number;
}

/** The pause was sent and Klipper did not say "paused" within 20 s, or it could not be sent (reason "send_failed"). */
export interface AutoPauseNotConfirmedEvent {
  job_id: number;
  printer_id: number;
  incident_id?: number | null;
  reason: "timeout" | "send_failed";
  last_state?: string;
  error?: string;
}

export interface AutoPauseFailedEvent {
  job_id: number;
  printer_id: number;
  reason: string;
  incident_id?: number | null;
}

/** Warn mode (AUTO_PAUSE_MODE=warn): the streak was reached and the pause would have been sent. */
export interface AutoPauseWouldPauseEvent {
  job_id: number;
  printer_id: number;
  reason: string;
  consecutive_layers: number;
  layer: number | null;
  confidence: number | null;
  incident_id?: number | null;
}

/** incident.opened / incident.updated: enough to know an incident exists and where it stands. */
export interface IncidentEvent {
  incident_id: number;
  printer_id: number;
  job_id: number;
  reason: string;
  mode: string | null;
  defect_class: string;
  status: string;
  outcome: string | null;
  opened_at: string;
}
