import { useContext, useEffect } from "react";
import { WebSocketContext, type WsListener } from "../context/WebSocketContext";
import type { WsEnvelope, WsEventType } from "../types/ws";

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
}

/** Subscribes to one WS event type for the lifetime of the component. */
export function useWsEvent<T = unknown>(eventType: WsEventType | "*", callback: (envelope: WsEnvelope<T>) => void) {
  const { subscribe } = useWebSocket();

  useEffect(() => {
    return subscribe(eventType, callback as WsListener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, subscribe]);
}
