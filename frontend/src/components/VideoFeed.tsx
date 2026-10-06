import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { API_BASE_URL } from "../services/apiClient";

/** MJPEG stream via a plain <img> - no custom JS needed for the multipart/x-mixed-replace
 * mechanics, the browser handles repainting on each part on its own. Token goes as a query
 * param since <img> can't set an Authorization header (same constraint as the WS contract). */
export function VideoFeed({ cameraId }: { cameraId: number }) {
  const { token } = useAuth();
  const [failed, setFailed] = useState(false);

  if (!token || failed) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-900 text-xs text-slate-400">
        Sin señal
      </div>
    );
  }

  const src = `${API_BASE_URL}/api/v1/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;

  return <img src={src} alt={`Cámara ${cameraId}`} className="h-full w-full object-cover" onError={() => setFailed(true)} />;
}
