import { VideoOff } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { feedState } from "../lib/feedState";
import { fetchSnapshot, type Snapshot } from "../services/bedMap";

/** A camera picture that refreshes with a still every few seconds, for thumbnails. Unlike the live video
 * (an MJPEG stream, a connection held open the whole time the page is open, ~1 MB/s at 6 frames/s), each
 * request here is short and gives its connection back: a browser allows about 6 per server, and every tab
 * with a live video keeps one. Pauses while the tab is hidden. */
export function SnapshotFeed({ cameraId, intervalMs = 2000 }: { cameraId: number; intervalMs?: number }) {
  const { token } = useAuth();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let current: string | null = null;
    let timer: number | undefined;

    const tick = async () => {
      if (!document.hidden) {
        try {
          const next = await fetchSnapshot(token, cameraId);
          if (cancelled) {
            URL.revokeObjectURL(next.url);
            return;
          }
          const previous = current;
          current = next.url;
          setSnapshot(next);
          setFailed(false);
          if (previous) URL.revokeObjectURL(previous);
        } catch {
          if (!cancelled) setFailed(true);
        }
      }
      if (!cancelled) timer = window.setTimeout(tick, intervalMs);
    };
    void tick();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (current) URL.revokeObjectURL(current);
    };
  }, [token, cameraId, intervalMs]);

  const state = feedState(snapshot, failed);
  if (state === "loading") return <div className="h-full w-full bg-surface-2" aria-hidden />;
  if (state === "error" || state === "stale" || !snapshot) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-surface-2 text-xs text-faint">
        <VideoOff size={20} />
        Sin señal
      </div>
    );
  }
  return <img src={snapshot.url} alt={`Cámara ${cameraId}`} className="h-full w-full object-cover" />;
}
