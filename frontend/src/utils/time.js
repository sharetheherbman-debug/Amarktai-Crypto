export const formatTimestamp = (timestamp, options = {}) => {
  const {
    includeTime = true,
    includeDate = true,
    includeSeconds = false,
    fallback = 'Not available',
    locale = 'en-US'
  } = options;

  if (!timestamp) {
    return fallback;
  }

  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    if (!date || Number.isNaN(date.getTime())) {
      return fallback;
    }

    const parts = [];
    if (includeDate) {
      parts.push(date.toLocaleDateString(locale));
    }
    if (includeTime) {
      const timeOptions = includeSeconds
        ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
        : { hour: '2-digit', minute: '2-digit' };
      parts.push(date.toLocaleTimeString(locale, timeOptions));
    }
    return parts.join(' ');
  } catch (error) {
    console.warn('formatTimestamp error:', error);
    return fallback;
  }
};
