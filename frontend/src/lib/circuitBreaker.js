/**
 * Global Circuit Breaker
 * 
 * Detects backend down state (multiple 502/503/504 errors) and prevents
 * request storms by pausing all API calls and real-time connections.
 * 
 * Circuit States:
 * - CLOSED: Normal operation (all requests allowed)
 * - OPEN: Backend detected as down (all requests blocked)
 * - HALF_OPEN: Testing if backend is back (limited requests allowed)
 */

class CircuitBreaker {
  constructor() {
    this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.failureCount = 0;
    this.successCount = 0;
    this.failureThreshold = 3; // Open circuit after 3 failures
    this.successThreshold = 2; // Close circuit after 2 successes in half-open
    this.timeout = 30000; // 30 seconds before trying half-open
    this.resetTimer = null;
    this.listeners = new Set();
    this.lastFailureTime = null;
    this.lastStateChange = Date.now();
  }

  /**
   * Record a successful request
   */
  recordSuccess() {
    if (this.state === 'OPEN') {
      return; // Don't count successes when open
    }

    this.failureCount = 0; // Reset failure count on success

    if (this.state === 'HALF_OPEN') {
      this.successCount++;
      if (this.successCount >= this.successThreshold) {
        this.closeCircuit();
      }
    }
  }

  /**
   * Record a failed request
   */
  recordFailure(error) {
    // Only count 502/503/504 errors and network errors
    const isServerError = 
      error?.response?.status === 502 ||
      error?.response?.status === 503 ||
      error?.response?.status === 504 ||
      error?.code === 'ERR_NETWORK' ||
      error?.code === 'ECONNABORTED';

    if (!isServerError) {
      return; // Don't count other errors (4xx, etc.)
    }

    this.lastFailureTime = Date.now();
    this.failureCount++;

    console.warn(`⚠️  Circuit breaker: Failure ${this.failureCount}/${this.failureThreshold}`, error.message || error);

    if (this.state === 'CLOSED' && this.failureCount >= this.failureThreshold) {
      this.openCircuit();
    } else if (this.state === 'HALF_OPEN') {
      this.openCircuit(); // Go back to open if half-open fails
    }
  }

  /**
   * Open the circuit (block all requests)
   */
  openCircuit() {
    if (this.state === 'OPEN') {
      return; // Already open
    }

    console.error('🔴 Circuit breaker OPEN - Backend appears down');
    this.state = 'OPEN';
    this.lastStateChange = Date.now();
    this.failureCount = 0;
    this.successCount = 0;
    this.notifyListeners();

    // Schedule transition to half-open
    if (this.resetTimer) {
      clearTimeout(this.resetTimer);
    }
    this.resetTimer = setTimeout(() => {
      this.halfOpenCircuit();
    }, this.timeout);
  }

  /**
   * Transition to half-open (allow test requests)
   */
  halfOpenCircuit() {
    console.log('🟡 Circuit breaker HALF-OPEN - Testing backend...');
    this.state = 'HALF_OPEN';
    this.lastStateChange = Date.now();
    this.successCount = 0;
    this.notifyListeners();
  }

  /**
   * Close the circuit (resume normal operation)
   */
  closeCircuit() {
    console.log('🟢 Circuit breaker CLOSED - Backend recovered');
    this.state = 'CLOSED';
    this.lastStateChange = Date.now();
    this.failureCount = 0;
    this.successCount = 0;
    this.notifyListeners();

    if (this.resetTimer) {
      clearTimeout(this.resetTimer);
      this.resetTimer = null;
    }
  }

  /**
   * Check if requests are allowed
   */
  isRequestAllowed() {
    return this.state !== 'OPEN';
  }

  /**
   * Get current circuit state
   */
  getState() {
    return {
      state: this.state,
      failureCount: this.failureCount,
      successCount: this.successCount,
      lastFailureTime: this.lastFailureTime,
      lastStateChange: this.lastStateChange,
      isDown: this.state === 'OPEN'
    };
  }

  /**
   * Subscribe to state changes
   */
  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Notify all listeners of state change
   */
  notifyListeners() {
    const state = this.getState();
    this.listeners.forEach(listener => {
      try {
        listener(state);
      } catch (error) {
        console.error('Circuit breaker listener error:', error);
      }
    });
  }

  /**
   * Reset the circuit breaker
   */
  reset() {
    this.state = 'CLOSED';
    this.failureCount = 0;
    this.successCount = 0;
    this.lastFailureTime = null;
    if (this.resetTimer) {
      clearTimeout(this.resetTimer);
      this.resetTimer = null;
    }
    this.notifyListeners();
  }
}

// Export singleton instance
export const circuitBreaker = new CircuitBreaker();

// For debugging
if (typeof window !== 'undefined') {
  window.circuitBreaker = circuitBreaker;
}
