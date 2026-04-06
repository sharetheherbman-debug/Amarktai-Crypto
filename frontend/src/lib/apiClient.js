/**
 * Unified API Client
 * 
 * Single axios instance with:
 * - Base URL configuration
 * - JWT authentication interceptor
 * - Timeout handling
 * - Retry strategy with exponential backoff
 * - Consistent error normalization
 * - Global circuit breaker for backend down detection
 */

import axios from 'axios';
import { toast } from 'sonner';
import { API_BASE } from './api';
import { circuitBreaker } from './circuitBreaker';

// Create axios instance with defaults
const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor - Add JWT token and check circuit breaker
apiClient.interceptors.request.use(
  (config) => {
    // Check circuit breaker
    if (!circuitBreaker.isRequestAllowed()) {
      const error = new Error('Circuit breaker is OPEN - backend appears down');
      error.code = 'CIRCUIT_OPEN';
      return Promise.reject(error);
    }

    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - Handle errors and retries
apiClient.interceptors.response.use(
  (response) => {
    // Successful response - notify circuit breaker
    circuitBreaker.recordSuccess();
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    // Record failure in circuit breaker
    circuitBreaker.recordFailure(error);

    // Guard: Only retry if we have a valid config object (502 errors may not have config)
    if (!originalRequest) {
      console.warn('⚠️ No request config available for retry (possibly 502/gateway error)');
      const normalizedError = normalizeError(error);
      return Promise.reject(normalizedError);
    }

    // Don't retry if already retried max times
    if (!originalRequest._retry) {
      originalRequest._retry = 0;
    }

    // Retry logic for specific error codes
    const shouldRetry = 
      error.code === 'ECONNABORTED' || // Timeout
      error.code === 'ERR_NETWORK' || // Network error
      (error.response && [408, 429, 500, 502, 503, 504].includes(error.response.status));

    if (shouldRetry && originalRequest._retry < 3) {
      originalRequest._retry += 1;

      // Exponential backoff: 1s, 2s, 4s
      const delay = Math.pow(2, originalRequest._retry - 1) * 1000;
      
      console.log(`🔄 Retrying request (attempt ${originalRequest._retry}/3) after ${delay}ms`);
      
      await new Promise(resolve => setTimeout(resolve, delay));
      
      return apiClient(originalRequest);
    }

    // Handle 401 Unauthorized — token expired or force-logout
    if (error.response?.status === 401) {
      const detail = error.response?.data?.detail;
      const isForceLogout = detail === 'FORCE_LOGOUT';

      if (isForceLogout) {
        console.warn('🚪 Admin force-logout triggered');
      } else {
        console.error('❌ Unauthorized - session expired or invalid token');
      }

      // Clear token
      localStorage.removeItem('token');

      // Only redirect if not already on login page
      if (!window.location.pathname.includes('/login')) {
        const reason = isForceLogout ? 'force_logout' : 'session_expired';
        console.log(`🔀 Redirecting to login (reason: ${reason})...`);
        // Emit event for React Router to handle — carry reason so UI can show correct message
        window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { reason } }));

        // Fallback: direct redirect after a short delay to allow event handling
        setTimeout(() => {
          if (!window.location.pathname.includes('/login')) {
            window.location.href = '/login';
          }
        }, 100);
      }
    }

    // Normalize error
    const normalizedError = normalizeError(error);
    return Promise.reject(normalizedError);
  }
);

/**
 * Normalize error to consistent format
 */
function normalizeError(error) {
  const normalized = {
    message: 'An unexpected error occurred',
    code: 'UNKNOWN_ERROR',
    status: null,
    details: null
  };

  if (error.response) {
    // Server responded with error status
    normalized.status = error.response.status;
    normalized.message = error.response.data?.detail || 
                        error.response.data?.message || 
                        error.response.statusText ||
                        `Server error (${error.response.status})`;
    normalized.code = error.response.data?.code || `HTTP_${error.response.status}`;
    normalized.details = error.response.data;
  } else if (error.request) {
    // Request made but no response
    normalized.message = 'No response from server';
    normalized.code = 'NO_RESPONSE';
  } else if (error.code === 'ECONNABORTED') {
    // Timeout
    normalized.message = 'Request timeout';
    normalized.code = 'TIMEOUT';
  } else if (error.code === 'ERR_NETWORK') {
    // Network error
    normalized.message = 'Network error - check your connection';
    normalized.code = 'NETWORK_ERROR';
  } else {
    // Something else
    normalized.message = error.message || 'An unexpected error occurred';
    normalized.code = error.code || 'UNKNOWN_ERROR';
  }

  // Attach original error for debugging
  normalized.originalError = error;
  normalized.response = error.response;
  normalized.config = error.config;

  return normalized;
}

/**
 * Safe fetch wrapper - returns { data, error }
 */
export async function safeFetch(url, options = {}) {
  try {
    const response = await apiClient({
      url,
      ...options
    });
    return { data: response.data, error: null };
  } catch (error) {
    if (options.notifyOnError) {
      notifyError(error);
    }
    return { data: null, error };
  }
}

export function notifyError(error, fallback = 'Something went wrong') {
  const message = error?.message || fallback;
  if (message) {
    toast.error(message);
  }
}

/**
 * GET request
 */
export async function get(url, config = {}) {
  const response = await apiClient.get(url, config);
  return response.data;
}

/**
 * POST request
 */
export async function post(url, data = {}, config = {}) {
  const response = await apiClient.post(url, data, config);
  return response.data;
}

/**
 * PUT request
 */
export async function put(url, data = {}, config = {}) {
  const response = await apiClient.put(url, data, config);
  return response.data;
}

/**
 * DELETE request
 */
export async function del(url, config = {}) {
  const response = await apiClient.delete(url, config);
  return response.data;
}

/**
 * PATCH request
 */
export async function patch(url, data = {}, config = {}) {
  const response = await apiClient.patch(url, data, config);
  return response.data;
}

// Named export for components that prefer it
export { apiClient };

// Default export for backward compatibility
export default apiClient;
