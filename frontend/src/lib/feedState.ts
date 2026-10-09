/** What a camera picture on screen is, given the last snapshot or the last failure. */
export type FeedState = "loading" | "live" | "stale" | "error";

/** A frame older than this is the last one of a camera that stopped (the backend uses the same limit for the
 * video stream: app/api/v1/cameras.py, _STALE_FRAME_SECONDS). */
export const STALE_FRAME_SECONDS = 15;

export function feedState(snapshot: { ageSeconds: number | null } | null, failed: boolean): FeedState {
  if (snapshot === null) return failed ? "error" : "loading";
  // A snapshot with no age is a frame from a capture process that does not record times: trust it.
  if (snapshot.ageSeconds !== null && snapshot.ageSeconds > STALE_FRAME_SECONDS) return "stale";
  return failed ? "error" : "live";
}
