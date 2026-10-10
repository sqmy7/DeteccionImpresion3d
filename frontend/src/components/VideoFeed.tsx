import { VideoOff } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { API_BASE_URL, freshToken } from "../services/apiClient";

const RETRY_AFTER_MS = 5000;

/** MJPEG stream via a plain <img> - no custom JS needed for the multipart/x-mixed-replace
 * mechanics, the browser handles repainting on each part on its own. Token goes as a query
 * param since <img> can't set an Authorization header (same constraint as the WS contract).
 *
 * The stream is one HTTP connection kept open for as long as the img exists, and a browser allows about
 * 6 per server across all its tabs: so it is closed while the tab is hidden, and a failed stream is
 * tried again after a few seconds instead of staying "Sin señal" until the page is reloaded. */
export function VideoFeed({ cameraId, fit = "cover" }: { cameraId: number; fit?: "cover" | "contain" }) {
  const { token } = useAuth();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [visible, setVisible] = useState(() => !document.hidden);

  useEffect(() => {
    const onChange = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  useEffect(() => {
    if (!failed) return;
    const timer = window.setTimeout(() => {
      setFailed(false);
      setAttempt((count) => count + 1);
    }, RETRY_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [failed]);

  if (!token || failed || !visible) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-surface-2 text-xs text-faint">
        <VideoOff size={20} />
        {visible ? "Sin señal" : "En pausa"}
      </div>
    );
  }

  const src = `${API_BASE_URL}/api/v1/cameras/${cameraId}/stream?token=${encodeURIComponent(freshToken(token))}&r=${attempt}`;

  return (
    <img
      src={src}
      alt={`Cámara ${cameraId}`}
      className={`h-full w-full ${fit === "cover" ? "object-cover" : "object-contain"}`}
      onError={() => setFailed(true)}
    />
  );
}
