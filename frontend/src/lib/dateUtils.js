/**
 * Date and Time Utilities
 * Provides safe timestamp formatting to prevent "Invalid Date" errors
 */

/**
 * Format a timestamp to a human-readable string
 * Handles null/undefined/invalid timestamps gracefully
 * 
 * @param {string|Date|null} timestamp - ISO timestamp string or Date object
 * @param {Object} options - Formatting options
 * @param {boolean} options.includeTime - Include time in output (default: true)
 * @param {boolean} options.includeDate - Include date in output (default: true)
 * @param {boolean} options.includeSeconds - Include seconds (default: false)
 * @param {string} options.fallback - Fallback text for invalid/null timestamps (default: "—")
 * @returns {string} Formatted timestamp or fallback
 */
export function formatTimestamp(timestamp, options = {}) {
  const {
    includeTime = true,
    includeDate = true,
    includeSeconds = false,
    fallback = "—"
  } = options;
  
  // Handle null/undefined/empty
  if (!timestamp) {
    return fallback;
  }
  
  try {
    // Parse timestamp
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return fallback;
    }
    
    // Format parts
    const parts = [];
    
    if (includeDate) {
      parts.push(date.toLocaleDateString());
    }
    
    if (includeTime) {
      const timeOptions = includeSeconds 
        ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
        : { hour: '2-digit', minute: '2-digit' };
      parts.push(date.toLocaleTimeString('en-US', timeOptions));
    }
    
    return parts.join(' ');
    
  } catch (error) {
    console.warn('formatTimestamp error:', error);
    return fallback;
  }
}

/**
 * Format a timestamp to relative time (e.g., "2 hours ago")
 * 
 * @param {string|Date|null} timestamp - ISO timestamp or Date
 * @param {string} fallback - Fallback text (default: "—")
 * @returns {string} Relative time string or fallback
 */
export function formatRelativeTime(timestamp, fallback = "—") {
  if (!timestamp) return fallback;
  
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    
    if (isNaN(date.getTime())) {
      return fallback;
    }
    
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    
    if (diffSec < 60) {
      return 'Just now';
    } else if (diffMin < 60) {
      return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
    } else if (diffHour < 24) {
      return `${diffHour} hour${diffHour !== 1 ? 's' : ''} ago`;
    } else if (diffDay < 7) {
      return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;
    } else {
      // Fall back to absolute date for older timestamps
      return formatTimestamp(timestamp, { includeTime: false });
    }
    
  } catch (error) {
    console.warn('formatRelativeTime error:', error);
    return fallback;
  }
}

/**
 * Format a timestamp to time only
 * 
 * @param {string|Date|null} timestamp
 * @param {boolean} includeSeconds - Include seconds (default: false)
 * @param {string} fallback - Fallback text (default: "—")
 * @returns {string}
 */
export function formatTime(timestamp, includeSeconds = false, fallback = "—") {
  return formatTimestamp(timestamp, {
    includeDate: false,
    includeTime: true,
    includeSeconds,
    fallback
  });
}

/**
 * Format a timestamp to date only
 * 
 * @param {string|Date|null} timestamp
 * @param {string} fallback - Fallback text (default: "—")
 * @returns {string}
 */
export function formatDate(timestamp, fallback = "—") {
  return formatTimestamp(timestamp, {
    includeDate: true,
    includeTime: false,
    fallback
  });
}

/**
 * Check if a timestamp is valid
 * 
 * @param {string|Date|null} timestamp
 * @returns {boolean}
 */
export function isValidTimestamp(timestamp) {
  if (!timestamp) return false;
  
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return !isNaN(date.getTime());
  } catch {
    return false;
  }
}
