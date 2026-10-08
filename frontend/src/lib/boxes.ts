import type { Detection } from "../types/api";

export interface FrameBox {
  className: string;
  confidence: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  // Which stored box it is (detection and position in raw_output.detections), to join it with
  // what the backend computes per box, such as the combined score.
  detectionId?: number;
  index?: number;
}

interface StoredFrame {
  width?: number;
  height?: number;
  roi?: { x: number; y: number; w: number; h: number };
}

/** A detection's boxes in normalized coordinates of the full frame. The model's boxes are relative
 * to the region it saw; newer detections record that region (raw_output.frame). The few earliest
 * detections stored boxes in pixels and are skipped. */
export function detectionBoxes(detection: Detection): FrameBox[] {
  const raw = detection.raw_output as { detections?: { class: string; confidence: number; box: number[] }[]; frame?: StoredFrame };
  const frame = raw.frame;
  const boxes: FrameBox[] = [];
  (raw.detections ?? []).forEach((item, index) => {
    const box = item.box ?? [];
    if (box.length !== 4 || box.some((value) => typeof value !== "number" || value < -0.01 || value > 1.01)) return;
    let [x1, y1, x2, y2] = box;
    if (frame?.roi && frame.width && frame.height) {
      const { x, y, w, h } = frame.roi;
      [x1, y1, x2, y2] = [(x + x1 * w) / frame.width, (y + y1 * h) / frame.height, (x + x2 * w) / frame.width, (y + y2 * h) / frame.height];
    }
    boxes.push({ className: item.class, confidence: item.confidence, x1, y1, x2, y2, detectionId: detection.id, index });
  });
  return boxes;
}
