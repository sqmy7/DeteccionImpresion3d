import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getWsUrl } from "../services/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { WsEnvelope, WsEventType } from "../types/ws";

export type WsListener = (envelope: WsEnvelope) => void;

interface WebSocketContextValue {
  connected: boolean;
  subscribe: (eventType: WsEventType | "*", listener: WsListener) => () => void;
  subscribeToPrinters: (printerIds: number[]) => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const WebSocketContext = createContext<WebSocketContextValue | undefined>(undefined);

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [connected, setConnected] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef<Map<string, Set<WsListener>>>(new Map());
  const reconnectTimeoutRef = useRef<number | undefined>(undefined);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);
  const intentionalCloseRef = useRef(false);

  const dispatch = useCallback((envelope: WsEnvelope) => {
    listenersRef.current.get(envelope.type)?.forEach((listener) => listener(envelope));
    listenersRef.current.get("*")?.forEach((listener) => listener(envelope));
  }, []);

  useEffect(() => {
    if (!token) {
      intentionalCloseRef.current = true;
      window.clearTimeout(reconnectTimeoutRef.current);
      socketRef.current?.close();
      socketRef.current = null;
      setConnected(false);
      return;
    }

    intentionalCloseRef.current = false;

    const connect = (currentToken: string) => {
      const socket = new WebSocket(getWsUrl(currentToken));
      socketRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
      };

      socket.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data) as WsEnvelope;
          dispatch(envelope);
        } catch {
          // Malformed frame - drop it, don't crash the app over a single bad message.
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (intentionalCloseRef.current) return;

        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
        reconnectTimeoutRef.current = window.setTimeout(() => connect(currentToken), delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect(token);

    return () => {
      intentionalCloseRef.current = true;
      window.clearTimeout(reconnectTimeoutRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [token, dispatch]);

  const subscribe = useCallback((eventType: WsEventType | "*", listener: WsListener) => {
    if (!listenersRef.current.has(eventType)) {
      listenersRef.current.set(eventType, new Set());
    }
    listenersRef.current.get(eventType)!.add(listener);

    return () => {
      listenersRef.current.get(eventType)?.delete(listener);
    };
  }, []);

  const subscribeToPrinters = useCallback((printerIds: number[]) => {
    socketRef.current?.send(JSON.stringify({ action: "subscribe", printer_ids: printerIds }));
  }, []);

  const value = useMemo(
    () => ({ connected, subscribe, subscribeToPrinters }),
    [connected, subscribe, subscribeToPrinters],
  );

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}
