import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { listCamerasForPrinter } from "../services/cameras";
import type { Camera, Printer } from "../types/api";
import { PrinterStatusBadge } from "./PrinterStatusBadge";
import { VideoFeed } from "./VideoFeed";

export function PrinterCard({ printer }: { printer: Printer }) {
  const { token } = useAuth();
  const [primaryCamera, setPrimaryCamera] = useState<Camera | null>(null);
  const [camerasLoaded, setCamerasLoaded] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    listCamerasForPrinter(token, printer.id)
      .then((cameras) => {
        if (cancelled) return;
        const primary = cameras.find((camera) => camera.role === "primary" && camera.is_active) ?? cameras[0] ?? null;
        setPrimaryCamera(primary);
      })
      .catch(() => {
        // No cameras configured yet, or the request failed - falls back to "sin cámara" below.
      })
      .finally(() => {
        if (!cancelled) setCamerasLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [token, printer.id]);

  return (
    <Link
      to={`/printers/${printer.id}`}
      className="block overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition hover:border-slate-300 hover:shadow-md"
    >
      <div className="aspect-video w-full bg-slate-900">
        {primaryCamera ? (
          <VideoFeed cameraId={primaryCamera.id} />
        ) : (
          camerasLoaded && (
            <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">
              Sin cámara configurada
            </div>
          )
        )}
      </div>

      <div className="flex items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-slate-900">{printer.name}</h3>
          <p className="truncate text-sm text-slate-500">{printer.model ?? "Modelo no especificado"}</p>
        </div>
        <PrinterStatusBadge status={printer.last_known_status} />
      </div>
    </Link>
  );
}
