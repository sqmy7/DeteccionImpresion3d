import { useEffect, useRef, useState } from "react";
import { classColor, classLabel } from "../config/defectClasses";
import { useWsEvent } from "../hooks/useWebSocket";
import type { DetectionBox, DetectionBoxesEvent } from "../types/ws";
import { VideoFeed } from "./VideoFeed";

const BOX_LINE_WIDTH = 2;
const LABEL_FONT = "600 13px system-ui, sans-serif";
const LABEL_PADDING_X = 5;
const LABEL_HEIGHT = 18;

/** Live camera feed with the latest per-layer detection boxes drawn on top. Inference runs once
 * per layer (not per video frame), so the boxes are a snapshot: they appear when a detection.boxes
 * event arrives for this camera and stay as-is - not re-drawn or cleared - until the next one,
 * empty or not. The canvas is resized to the container's actual rendered pixels (not a fixed
 * constant) so normalized 0..1 box coordinates land in the right place at any layout width. */
export function LiveCameraView({ cameraId, initialBoxes = [] }: { cameraId: number; initialBoxes?: DetectionBox[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [boxes, setBoxes] = useState<DetectionBox[]>([]);
  // Once a live event has arrived, it is newer than whatever the page loaded with.
  const liveEventSeen = useRef(false);

  // A different camera (e.g. navigating to another printer) starts with no boxes rather than
  // showing the previous camera's last detection for an instant.
  useEffect(() => {
    liveEventSeen.current = false;
    setBoxes([]);
  }, [cameraId]);

  // The last analyzed layer's boxes, loaded with the page: otherwise the view stays empty until the
  // next layer is analyzed, which can be a minute away.
  useEffect(() => {
    if (!liveEventSeen.current) setBoxes(initialBoxes);
  }, [initialBoxes]);

  useWsEvent<DetectionBoxesEvent>("detection.boxes", (envelope) => {
    if (envelope.data.camera_id !== cameraId) return;
    liveEventSeen.current = true;
    setBoxes(envelope.data.boxes);
  });

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const { clientWidth: width, clientHeight: height } = container;
      canvas.width = width * dpr;
      canvas.height = height * dpr;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      for (const box of boxes) {
        const color = classColor(box.class);
        const x = box.x1 * width;
        const y = box.y1 * height;
        const w = (box.x2 - box.x1) * width;
        const h = (box.y2 - box.y1) * height;

        ctx.lineWidth = BOX_LINE_WIDTH;
        ctx.strokeStyle = color;
        ctx.strokeRect(x, y, w, h);

        const label = `${classLabel(box.class)} ${box.confidence.toFixed(2)}`;
        ctx.font = LABEL_FONT;
        const labelWidth = ctx.measureText(label).width + LABEL_PADDING_X * 2;
        const labelY = y >= LABEL_HEIGHT ? y - LABEL_HEIGHT : y;

        ctx.fillStyle = color;
        ctx.fillRect(x, labelY, labelWidth, LABEL_HEIGHT);
        ctx.fillStyle = "#ffffff";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + LABEL_PADDING_X, labelY + LABEL_HEIGHT / 2 + 1);
      }
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(container);
    return () => observer.disconnect();
  }, [boxes]);

  return (
    <div ref={containerRef} className="relative aspect-video w-full overflow-hidden rounded-lg bg-surface-2">
      <VideoFeed cameraId={cameraId} />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
    </div>
  );
}
