/**
 * useRealtime Hook
 * 
 * React hook for connecting to the unified real-time system
 * Provides connection status, last update timestamps, and event subscriptions
 */

import { useState, useEffect, useCallback } from 'react';
import realtimeClient from '../lib/realtime';

/**
 * Hook for managing real-time connection
 */
export function useRealtimeConnection(token) {
  const [status, setStatus] = useState({
    connected: false,
    mode: 'disconnected',
    rtt: null,
    lastUpdate: {},
    reconnectAttempts: 0
  });

  useEffect(() => {
    if (!token) {
      return;
    }

    // Connect to real-time system
    realtimeClient.connect(token);

    // Listen for connection status changes
    const unsubscribe = realtimeClient.on('connection', (data) => {
      setStatus(realtimeClient.getStatus());
    });

    // Update status periodically
    const interval = setInterval(() => {
      setStatus(realtimeClient.getStatus());
    }, 1000);

    return () => {
      clearInterval(interval);
      unsubscribe();
      realtimeClient.disconnect();
    };
  }, [token]);

  return status;
}

/**
 * Hook for subscribing to real-time events
 * 
 * @param {string} eventType - Event type to subscribe to (trades, bots, balances, etc.)
 * @param {function} callback - Callback function to handle events
 * @param {array} deps - Dependencies array (like useEffect)
 * 
 * Note: Callback should be memoized with useCallback to avoid unnecessary re-subscriptions
 */
export function useRealtimeEvent(eventType, callback, deps = []) {
  useEffect(() => {
    const unsubscribe = realtimeClient.on(eventType, callback);
    return unsubscribe;
  }, [eventType, callback, ...deps]); // Explicitly list all dependencies
}

/**
 * Hook for getting last update timestamp for an event type
 */
export function useLastUpdate(eventType) {
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    const interval = setInterval(() => {
      const status = realtimeClient.getStatus();
      setLastUpdate(status.lastUpdate[eventType] || null);
    }, 5000);

    return () => clearInterval(interval);
  }, [eventType]);

  return lastUpdate;
}

/**
 * Hook for sending messages to the server
 */
export function useRealtimeSend() {
  return useCallback((message) => {
    realtimeClient.send(message);
  }, []);
}

/**
 * Complete hook with all functionality
 */
export default function useRealtime(eventType = null, callback = null) {
  const token = localStorage.getItem('token');
  const connection = useRealtimeConnection(token);
  const lastUpdate = useLastUpdate(eventType);
  const send = useRealtimeSend();

  // Subscribe to event if provided
  useEffect(() => {
    if (eventType && callback) {
      return realtimeClient.on(eventType, callback);
    }
  }, [eventType, callback]);

  return {
    connection,
    lastUpdate,
    send,
    on: realtimeClient.on.bind(realtimeClient),
    off: realtimeClient.off.bind(realtimeClient)
  };
}
