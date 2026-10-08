import { VideoOff } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { API_BASE_URL } from "../services/apiClient";

/** MJPEG stream via a plain <img> - no custom JS needed for the multipart/x-mixed-replace
 * mechanics, the browser handles repainting on each part on its own. Token goes as a query
 * param since <img> can't set an Authorization header (same constraint as the WS contract). */
export function VideoFeed({ cameraId, fit = "cover" }: { cameraId: number; fit?: "cover" | "contain" }) {
  const { token } = useAuth();
  const [failed, setFailed] = useState(false);

  if (!token || failed) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-surface-2 text-xs text-faint">
        <VideoOff size={20} />
        Sin señal
      </div>
    );
  }

  const src = `${API_BASE_URL}/api/v1/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;

  return (
    <img
      src={src}
      alt={`Cámara ${cameraId}`}
      className={`h-full w-full ${fit === "cover" ? "object-cover" : "object-contain"}`}
      onError={() => setFailed(true)}
    />
  );
}
