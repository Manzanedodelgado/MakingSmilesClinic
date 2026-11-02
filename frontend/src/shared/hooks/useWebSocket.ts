"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface WSMessage {
  event: string;
  data: any;
  timestamp: string;
}

interface UseWebSocketOptions {
  url: string;
  onMessage?: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
  reconnect?: boolean;
  reconnectInterval?: number;
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnect = true,
  reconnectInterval = 5000,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectingRef = useRef(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectingRef.current = false;
      onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        setLastMessage(msg);
        onMessage?.(msg);
      } catch (e) {
        console.error("Error parseando WS:", e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      onClose?.();
      
      if (reconnect && !reconnectingRef.current) {
        reconnectingRef.current = true;
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectingRef.current = false;
          connect();
        }, reconnectInterval);
      }
    };

    ws.onerror = (err) => {
      onError?.(err);
    };
  }, [url, onMessage, onOpen, onClose, onError, reconnect, reconnectInterval]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    reconnectingRef.current = true;
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
  };
}