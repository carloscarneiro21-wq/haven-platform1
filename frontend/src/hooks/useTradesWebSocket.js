/**
 * useTradesWebSocket - Custom hook for WebSocket connection to trades stream
 * 
 * Features:
 * - JWT-authenticated WebSocket connection via query param
 * - Auto-reconnect with exponential backoff (1s, 2s, 5s, 10s max)
 * - Fallback to polling when WS disconnected >10s
 * - Subscription management
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/App";

const WS_RECONNECT_BASE_DELAY = 1000;
const WS_RECONNECT_MAX_DELAY = 30000;
const POLLING_FALLBACK_DELAY = 10000; // Start polling mode after 10s disconnected
const WS_PATH = process.env.REACT_APP_WS_PATH || "/api/ws/stream";

export function useTradesWebSocket(token, options = {}) {
  const { onTrade, onMetrics, autoConnect = true } = options;
  
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);
  const [lastMessage, setLastMessage] = useState(null);
  const [usingPolling, setUsingPolling] = useState(false);
  
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeout = useRef(null);
  const pollingFallbackTimeout = useRef(null);
  const connectRef = useRef(null);
  const subscriptions = useRef(new Set());
  const filters = useRef({});
  const disconnectedAt = useRef(null);
  
  // Get WebSocket URL - handles production correctly
  const getWsUrl = useCallback(() => {
    const backendUrl = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    
    // Parse the URL to get components
    let wsUrl;
    try {
      const url = new URL(backendUrl);
      // Convert protocol
      const wsProtocol = url.protocol === "https:" ? "wss:" : "ws:";
      // Build WS URL
      wsUrl = `${wsProtocol}//${url.host}${WS_PATH}`;
    } catch (e) {
      // Fallback: simple string replacement
      const wsProtocol = backendUrl.startsWith("https") ? "wss" : "ws";
      wsUrl = backendUrl.replace(/^https?/, wsProtocol) + WS_PATH;
    }
    
    // Add token as query param (browser WS doesn't support custom headers)
    if (token) {
      wsUrl += `?token=${encodeURIComponent(token)}`;
    }
    
    console.log("[WS] URL:", wsUrl.substring(0, 60) + "...");
    return wsUrl;
  }, [token]);

  // Track last message time for liveness checks
  const lastMessageAtRef = useRef(0);
  const heartbeatIntervalRef = useRef(null);
  
  // Mark polling mode (actual polling is handled by the page to avoid duplicate fetch loops)
  const startPolling = useCallback(() => {
    setUsingPolling(true);
    console.log("[WS] Polling mode ON (page-controlled polling)");
  }, []);

  // Stop polling mode
  const stopPolling = useCallback(() => {
    if (pollingFallbackTimeout.current) {
      clearTimeout(pollingFallbackTimeout.current);
      pollingFallbackTimeout.current = null;
    }
    setUsingPolling(false);
  }, []);
  
  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!token) {
      console.warn("[WS] Cannot connect: No token");
      return;
    }
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log("[WS] Already connected");
      return;
    }
    
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log("[WS] Already connecting");
      return;
    }
    
    setConnecting(true);
    setError(null);
    
    try {
      const wsUrl = getWsUrl();
      console.log("[WS] Connecting...");
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log("[WS] Connected successfully!");

        if (reconnectTimeout.current) {
          clearTimeout(reconnectTimeout.current);
          reconnectTimeout.current = null;
        }
        setConnected(true);
        setConnecting(false);
        setError(null);
        reconnectAttempts.current = 0;
        disconnectedAt.current = null;
        lastMessageAtRef.current = Date.now();

        // Start client-side heartbeat / liveness watchdog
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }
        heartbeatIntervalRef.current = setInterval(() => {
          try {
            // Force reconnect if no messages for 60s
            if (Date.now() - lastMessageAtRef.current > 60000) {
              console.log("[WS] No messages for 60s, forcing reconnect");
              ws.close(4000, "stale_client");
              return;
            }
            // Send ping (server accepts and replies pong)
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "ping", ts: new Date().toISOString() }));
            }
          } catch (_) {
            // ignore
          }
        }, 25000);
        
        // Stop polling since WS is connected
        stopPolling();
        
        // Subscribe to topics after small delay to ensure server is ready
        setTimeout(() => {
          if (ws.readyState === WebSocket.OPEN) {
            const subMsg = {
              type: "subscribe",
              topics: ["trades", "metrics"],
              filters: { mode: "paper" },
            };
            ws.send(JSON.stringify(subMsg));
            console.log("[WS] Subscribed to trades and metrics");
          }
        }, 100);
      };
      
      ws.onmessage = (event) => {
        try {
          lastMessageAtRef.current = Date.now();
          const message = JSON.parse(event.data);
          setLastMessage(message);
          
          // Handle different message types
          switch (message.type) {
            case "trade.created":
            case "trade.updated":
              console.log("[WS] Trade event:", message.type, message.data?.id);
              onTrade?.(message);
              break;
            case "metrics.updated":
              onMetrics?.(message);
              break;
            case "connected":
              console.log("[WS] Server confirmed connection:", message.user?.username);
              break;
            case "subscribed":
              console.log("[WS] Server confirmed subscription:", message.topics);
              break;
            case "ping":
              // Server keepalive ping -> respond pong
              ws.send(JSON.stringify({ type: "pong", ts: new Date().toISOString() }));
              break;
            case "pong":
            case "pong.ack":
            case "heartbeat":
              // Heartbeat - connection is alive
              break;
            default:
              console.log("[WS] Message:", message.type);
          }
        } catch (e) {
          console.error("[WS] Parse error:", e);
        }
      };
      
      ws.onerror = (event) => {
        console.error("[WS] Error event:", event);
        setError("WebSocket connection error");
      };
      
      ws.onclose = (event) => {
        console.log("[WS] Closed:", event.code, event.reason);
        setConnected(false);
        setConnecting(false);
        wsRef.current = null;

        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }
        
        // Track disconnection time for polling fallback
        if (!disconnectedAt.current) {
          disconnectedAt.current = Date.now();
        }
        
        // Handle auth failure - don't reconnect
        if (event.code === 4401) {
          console.error("[WS] Authentication failed - not reconnecting");
          setError("Authentication failed");
          // Start polling immediately for auth failures
          startPolling();
          return;
        }

        // Normal close requested by client (logout/unmount)
        if (event.code === 1000 && event.reason === "Client disconnect") {
          return;
        }
        
        // Start polling mode after delay
        if (!pollingFallbackTimeout.current) {
          pollingFallbackTimeout.current = setTimeout(() => {
            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
              console.log("[WS] Disconnected too long, enabling polling mode");
              startPolling();
            }
          }, POLLING_FALLBACK_DELAY);
        }
        
        // Auto-reconnect with exponential backoff + jitter
        const baseDelay = Math.min(
          WS_RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts.current),
          WS_RECONNECT_MAX_DELAY
        );
        const jitter = baseDelay * 0.2 * (Math.random() * 2 - 1); // +/- 20%
        const delay = Math.max(250, Math.floor(baseDelay + jitter));
        
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current + 1})...`);
        reconnectAttempts.current += 1;
        
        reconnectTimeout.current = setTimeout(() => {
          connectRef.current?.();
        }, delay);
      };
      
    } catch (e) {
      console.error("[WS] Connection error:", e);
      setError(e.message);
      setConnecting(false);
      startPolling();
    }

  }, [token, getWsUrl, onTrade, onMetrics, startPolling, stopPolling]);

  // Keep latest connect in a ref (avoid stale closure + lint rule about forward reference)
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);
  
  // Disconnect
  const disconnect = useCallback(() => {
    console.log("[WS] Disconnecting...");
    
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
      reconnectTimeout.current = null;
    }

    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    
    stopPolling();
    
    if (wsRef.current) {
      wsRef.current.close(1000, "Client disconnect");
      wsRef.current = null;
    }
    
    setConnected(false);
    reconnectAttempts.current = 0;
  }, [stopPolling]);
  
  // Subscribe to topics
  const subscribe = useCallback((topics, newFilters = {}) => {
    topics.forEach(t => subscriptions.current.add(t));
    filters.current = { ...filters.current, ...newFilters };
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "subscribe",
        topics: Array.from(subscriptions.current),
        filters: filters.current,
      }));
    }
  }, []);
  
  // Unsubscribe from topics
  const unsubscribe = useCallback((topics) => {
    topics.forEach(t => subscriptions.current.delete(t));
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "unsubscribe",
        topics,
      }));
    }
  }, []);
  
  // Send ping
  const ping = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ping" }));
    }
  }, []);
  
  // Auto-connect on mount (wait for token to be available)
  useEffect(() => {
    if (autoConnect && token) {
      console.log("[WS] Token available, will connect in 500ms");
      // Small delay to ensure component is mounted
      const timer = setTimeout(() => {
        connect();
      }, 500);
      return () => clearTimeout(timer);
    } else if (autoConnect && !token) {
      console.log("[WS] Waiting for token...");
    }
  }, [autoConnect, token, connect]);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);
  
  return {
    connected,
    connecting,
    error,
    lastMessage,
    usingPolling,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    ping,
  };
}

export default useTradesWebSocket;
