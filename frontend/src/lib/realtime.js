/**
 * Unified Real-Time Client
 * 
 * Handles WebSocket connections with JWT authentication and polling fallback.
 * Provides event bus for: trades, bots, balances, decisions, metrics, whale,
 * alerts, system_health, wallet, ai_tasks
 */

import { wsUrl, API_BASE } from './api';

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
    this.pollingIntervals = new Map();
    this.lastUpdate = {};
    this.connectionMode = 'disconnected'; // 'ws', 'sse', 'polling', 'disconnected'
    this.pingInterval = null;
    this.pongTimeout = null;
    this.rtt = null;
    this._reconnectTimer = null;
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
    const { type, data, ts } = message;

    if (!type) {
      console.warn('⚠️  Message without type:', message);
      return;
    }

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

    // Emit to listeners
    this.emit(type, data);
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
   * Schedule reconnection with exponential backoff
   */
  scheduleReconnect() {
    // Do not reconnect if token was cleared (logged out)
    if (!this.token) {
      console.log('🔌 Skipping reconnect — not authenticated');
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('❌ Max reconnect attempts reached - falling back to SSE');
      this.startSSE();
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      // Re-check auth before actually reconnecting
      if (!this.token) return;
      this.connectWebSocket();
    }, delay);
  }

  /**
   * Start SSE (Server-Sent Events) fallback
   */
  startSSE() {
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
    if (this.connectionMode === 'polling') {
      return; // Already polling
    }

    console.log('📡 Starting polling fallback');
    this.connectionMode = 'polling';
    this.emit('connection', { status: 'connected', mode: 'polling' });

    // Poll different endpoints at different intervals
    // Use API_BASE so paths work with any deployment config (no double /api/)
    const pollingConfig = [
      { type: 'trades', endpoint: `${API_BASE}/trades/recent?limit=50`, interval: 5000 },
      { type: 'bots', endpoint: `${API_BASE}/bots`, interval: 10000 },
      { type: 'balances', endpoint: `${API_BASE}/wallet/balances`, interval: 15000 },
      { type: 'metrics', endpoint: `${API_BASE}/portfolio/summary`, interval: 10000 },
      { type: 'system_health', endpoint: `${API_BASE}/system/health`, interval: 30000 },
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
   * Disconnect and clear all connections + timers
   */
  disconnect() {
    console.log('🔌 Disconnecting...');
    
    // Cancel any pending reconnect
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    
    this.token = null;
    this.stopPing();
    this.stopSSE();
    this.stopPolling();
    
    if (this.ws) {
      this.ws.onclose = null; // prevent onclose from triggering reconnect
      this.ws.close();
      this.ws = null;
    }
    
    this.connected = false;
    this.connectionMode = 'disconnected';
    this.reconnectAttempts = 0;
    this.listeners.clear();
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
