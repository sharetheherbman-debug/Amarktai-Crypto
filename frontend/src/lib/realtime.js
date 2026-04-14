/**
 * Unified Real-Time Client
 * 
 * Handles WebSocket connections with JWT authentication and polling fallback.
 * Provides event bus for: trades, bots, balances, decisions, metrics, whale,
 * alerts, system_health, wallet, ai_tasks
 * 
 * Features:
 * - Exponential backoff with jitter for reconnects
 * - Circuit breaker integration
 * - Automatic fallback: WebSocket → SSE → Polling
 */

import { wsUrl, API_BASE } from './api';
import { circuitBreaker } from './circuitBreaker';

class RealtimeClient {
  constructor() {
    this.ws = null;
    this.eventSource = null;
    this.token = null;
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start at 1 second
    this.maxReconnectDelay = 30000; // Max 30 seconds
    this.listeners = new Map();
    this.rawListeners = new Set(); // Receive every raw message before typed dispatch
    this.pollingIntervals = new Map();
    this.lastUpdate = {};
    this.connectionMode = 'disconnected'; // 'ws', 'sse', 'polling', 'disconnected'
    this.pingInterval = null;
    this.pongTimeout = null;
    this.rtt = null;
  }

  /**
   * Connect to WebSocket with JWT token
   */
  connect(token) {
    if (!token) {
      console.error('❌ Cannot connect: No token provided');
      return;
    }

    this.token = token;
    this.connectWebSocket();
  }

  /**
   * Establish WebSocket connection
   */
  connectWebSocket() {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const url = `${wsUrl()}?token=${this.token}`;
      // Mask token in logs - replace query parameter value
      const maskedUrl = url.replace(/token=[^&]*/, 'token=***');
      console.log('🔌 Connecting to WebSocket:', maskedUrl);
      
      this.ws = new WebSocket(url);
      
      this.ws.onopen = () => {
        console.log('✅ WebSocket connected');
        this.connected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.connectionMode = 'ws';
        this.emit('connection', { status: 'connected', mode: 'ws' });
        this.startPing();
        this.stopPolling(); // Stop polling if it was active
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('❌ WebSocket message parse error:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        this.emit('connection', { status: 'error', mode: 'ws' });
      };

      this.ws.onclose = () => {
        console.log('🔌 WebSocket closed');
        this.connected = false;
        this.connectionMode = 'disconnected';
        this.stopPing();
        this.emit('connection', { status: 'disconnected' });
        this.scheduleReconnect();
      };
    } catch (error) {
      console.error('❌ WebSocket connection error:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Handle incoming WebSocket message
   */
  handleMessage(message) {
    const { type, data, ts, ...rest } = message;

    if (!type) {
      console.warn('⚠️  Message without type:', message);
      return;
    }

    // Deliver raw message to raw listeners FIRST (before typed dispatch).
    // This lets useDashboardState subscribe once and handle all event types
    // without opening a second WebSocket connection.
    this.rawListeners.forEach(cb => {
      try { cb(message); } catch (e) { console.error('Raw listener error for message type', message?.type, ':', e); }
    });

    // Handle ping/pong
    if (type === 'ping') {
      this.send({ type: 'pong', timestamp: message.timestamp });
      return;
    }

    if (type === 'pong') {
      if (this.pongTimeout) {
        clearTimeout(this.pongTimeout);
        this.pongTimeout = null;
      }
      if (message.timestamp) {
        this.rtt = Date.now() - message.timestamp;
      }
      return;
    }

    // Update last update timestamp
    this.lastUpdate[type] = ts || new Date().toISOString();

    // When the backend sends a flat payload (no 'data' wrapper), pass the
    // remaining fields so listeners receive a useful object instead of undefined.
    const payload = data !== undefined ? data : (Object.keys(rest).length > 0 ? rest : undefined);

    // Emit to listeners
    this.emit(type, payload);

    // Alias backend event names to the canonical frontend names expected by
    // components (e.g. LiveTradesPanel listens on 'trades', not 'trade_executed').
    if (type === 'trade_executed') {
      this.emit('trades', payload);
    }
    if (type === 'balance_updated') {
      this.emit('balances', payload);
    }
  }

  /**
   * Send message to server
   */
  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Start ping/pong keepalive
   */
  startPing() {
    this.stopPing();
    
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        const timestamp = Date.now();
        this.send({ type: 'ping', timestamp });
        
        // Set pong timeout
        this.pongTimeout = setTimeout(() => {
          console.warn('⚠️  Pong timeout - connection may be dead');
          this.ws?.close();
        }, 10000); // 10 second timeout
      }
    }, 20000); // Ping every 20 seconds
  }

  /**
   * Stop ping/pong
   */
  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
    if (this.pongTimeout) {
      clearTimeout(this.pongTimeout);
      this.pongTimeout = null;
    }
  }

  /**
   * Schedule reconnection with exponential backoff + jitter
   */
  scheduleReconnect() {
    // Don't reconnect if no token
    if (!this.token) {
      console.log('⏸️  No token available - skipping reconnect');
      return;
    }

    // Check circuit breaker state
    const cbState = circuitBreaker.getState();
    if (cbState.isDown) {
      console.log('⏸️  Circuit breaker is OPEN - pausing WebSocket reconnect');
      // Check again after circuit breaker timeout
      setTimeout(() => this.scheduleReconnect(), 5000);
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ Max reconnect attempts reached - falling back to SSE');
      this.startSSE();
      return;
    }

    this.reconnectAttempts++;
    
    // Exponential backoff with jitter
    const baseDelay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    const jitter = Math.random() * 5000; // 0-5 seconds of random jitter
    const delay = Math.min(baseDelay + jitter, this.maxReconnectDelay);

    console.log(`🔄 Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      this.connectWebSocket();
    }, delay);
  }

  /**
   * Start SSE (Server-Sent Events) fallback
   */
  startSSE() {
    // Don't start SSE if no token
    if (!this.token) {
      console.log('⏸️  No token available - skipping SSE');
      return;
    }

    if (this.connectionMode === 'sse') {
      return; // Already using SSE
    }

    console.log('📡 Starting SSE fallback');
    this.connectionMode = 'sse';
    this.emit('connection', { status: 'connected', mode: 'sse' });

    try {
      const tokenParam = this.token ? `?token=${encodeURIComponent(this.token)}` : '';
      const eventSource = new EventSource(`${API_BASE}/realtime/events${tokenParam}`);

      eventSource.onopen = () => {
        console.log('✅ SSE connected');
        this.connected = true;
      };

      eventSource.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('❌ SSE message parse error:', error);
        }
      };

      eventSource.onerror = (error) => {
        console.error('❌ SSE error:', error);
        eventSource.close();
        this.connected = false;
        this.connectionMode = 'disconnected';
        this.emit('connection', { status: 'error', mode: 'sse' });
        // Fall back to polling if SSE fails
        setTimeout(() => this.startPolling(), 2000);
      };

      this.eventSource = eventSource;
    } catch (error) {
      console.error('❌ SSE connection error:', error);
      this.startPolling();
    }
  }

  /**
   * Stop SSE
   */
  stopSSE() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /**
   * Start polling fallback
   */
  startPolling() {
    // Don't start polling if no token
    if (!this.token) {
      console.log('⏸️  No token available - skipping polling');
      return;
    }

    if (this.connectionMode === 'polling') {
      return; // Already polling
    }

    console.log('📡 Starting polling fallback');
    this.connectionMode = 'polling';
    this.emit('connection', { status: 'connected', mode: 'polling' });

    // Poll different endpoints at different intervals
    const pollingConfig = [
      { type: 'trades', endpoint: '/api/trades/recent?limit=50', interval: 5000 },
      { type: 'bots', endpoint: '/api/bots', interval: 10000 },
      { type: 'balances', endpoint: '/api/wallet/balances', interval: 15000 },
      { type: 'metrics', endpoint: '/api/portfolio/summary', interval: 10000 },
      { type: 'system_health', endpoint: '/api/system/health', interval: 30000 },
    ];

    pollingConfig.forEach(({ type, endpoint, interval }) => {
      const poll = async () => {
        try {
          const response = await fetch(endpoint, {
            headers: {
              'Authorization': `Bearer ${this.token}`
            }
          });
          
          if (response.ok) {
            const data = await response.json();
            this.lastUpdate[type] = new Date().toISOString();
            this.emit(type, data);
          }
        } catch (error) {
          console.error(`❌ Polling error for ${type}:`, error);
        }
      };

      // Initial poll
      poll();

      // Set up interval
      const intervalId = setInterval(poll, interval);
      this.pollingIntervals.set(type, intervalId);
    });
  }

  /**
   * Stop polling
   */
  stopPolling() {
    if (this.pollingIntervals.size === 0) {
      return;
    }

    console.log('🛑 Stopping polling');
    this.pollingIntervals.forEach((intervalId) => {
      clearInterval(intervalId);
    });
    this.pollingIntervals.clear();
  }

  /**
   * Subscribe to event type
   */
  on(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type).add(callback);

    // Return unsubscribe function
    return () => {
      this.off(type, callback);
    };
  }

  /**
   * Unsubscribe from event type
   */
  off(type, callback) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).delete(callback);
    }
  }

  /**
   * Emit event to listeners
   */
  emit(type, data) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`❌ Listener error for ${type}:`, error);
        }
      });
    }
  }

  /**
   * Subscribe to ALL raw messages (before typed dispatch).
   * Returns an unsubscribe function.
   * Use this to avoid opening a second WebSocket connection.
   */
  onRawMessage(callback) {
    this.rawListeners.add(callback);
    return () => this.rawListeners.delete(callback);
  }

  /**
   * Disconnect
   */
  disconnect() {
    console.log('🔌 Disconnecting...');
    
    this.stopPing();
    this.stopSSE();
    this.stopPolling();
    
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    
    this.connected = false;
    this.connectionMode = 'disconnected';
    this.listeners.clear();
    this.rawListeners.clear();
    this.lastUpdate = {};
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      connected: this.connected,
      mode: this.connectionMode,
      rtt: this.rtt,
      lastUpdate: this.lastUpdate,
      reconnectAttempts: this.reconnectAttempts
    };
  }
}

// Singleton instance
const realtimeClient = new RealtimeClient();

export default realtimeClient;
