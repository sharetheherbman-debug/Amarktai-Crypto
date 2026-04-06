/**
 * ConnectionStatus Component
 * 
 * Shows an unobtrusive banner when backend is down (circuit breaker open)
 * or when real-time connection is reconnecting.
 */

import { useState, useEffect } from 'react';
import { circuitBreaker } from '@/lib/circuitBreaker';
import { AlertCircle, Wifi, WifiOff } from 'lucide-react';

export default function ConnectionStatus() {
  const [circuitState, setCircuitState] = useState(circuitBreaker.getState());
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Subscribe to circuit breaker state changes
    const unsubscribe = circuitBreaker.subscribe((state) => {
      setCircuitState(state);
      setIsVisible(state.isDown);
    });

    // Initial check
    const initialState = circuitBreaker.getState();
    setCircuitState(initialState);
    setIsVisible(initialState.isDown);

    return unsubscribe;
  }, []);

  if (!isVisible) {
    return null;
  }

  return (
    <div 
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center py-2 px-4"
      style={{
        background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.95) 0%, rgba(220, 38, 38, 0.95) 100%)',
        backdropFilter: 'blur(10px)',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
      }}
    >
      <div className="flex items-center gap-2 text-white font-medium text-sm">
        <WifiOff size={16} className="animate-pulse" />
        <span>
          Reconnecting to server...
        </span>
        <span className="text-xs opacity-80">
          ({circuitState.state === 'OPEN' ? 'Retrying in 30s' : 'Testing connection'})
        </span>
      </div>
    </div>
  );
}
