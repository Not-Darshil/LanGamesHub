import { useEffect, useRef, useState } from "react";

/** Close codes sent by the server (see backend app/realtime/hub.py). */
export const CLOSE_UNAUTHENTICATED = 4401;
export const CLOSE_FORBIDDEN = 4403;
export const CLOSE_KICKED = 4000;
export const CLOSE_TOO_MANY = 4429;
const TERMINAL_CODES = new Set([CLOSE_UNAUTHENTICATED, CLOSE_FORBIDDEN, CLOSE_KICKED, CLOSE_TOO_MANY]);

export interface SocketStatus {
  connected: boolean;
  /** Set when the server ended the connection for good (no auto-reconnect). */
  closedWith: number | null;
}

/**
 * Keeps a WebSocket open to `path`, reconnecting with backoff after network drops.
 * Every server message is passed to `onMessage`. Pass `enabled=false` to close it.
 */
export function useSocket(
  path: string,
  enabled: boolean,
  onMessage: (message: Record<string, unknown>) => void,
  generation = 0,
): SocketStatus {
  const [status, setStatus] = useState<SocketStatus>({ connected: false, closedWith: null });
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let retryTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}${path}`);
      socket.onopen = () => {
        attempt = 0;
        setStatus({ connected: true, closedWith: null });
        pingTimer = window.setInterval(() => socket?.send(JSON.stringify({ type: "ping" })), 25000);
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(String(event.data));
          if (message && typeof message === "object") handler.current(message);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = (event) => {
        window.clearInterval(pingTimer);
        if (stopped) return;
        if (TERMINAL_CODES.has(event.code)) {
          setStatus({ connected: false, closedWith: event.code });
          return;
        }
        setStatus({ connected: false, closedWith: null });
        const delay = Math.min(10000, 500 * 2 ** attempt++);
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    setStatus({ connected: false, closedWith: null });
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      window.clearInterval(pingTimer);
      socket?.close();
    };
  }, [path, enabled, generation]);

  return status;
}
