import { useState, useEffect } from 'react';
import { Badge } from './ui/badge';
import { API_BASE } from '../lib/api';

/**
 * VersionBadge Component
 * 
 * Displays the current build version of frontend and backend.
 * Fetches version info from /api/build/info endpoint (no auth required).
 * 
 * TASK G - Footer fix: Only show build badge when explicitly enabled
 * or when in admin view. Default footer shows copyright only.
 */
export default function VersionBadge({ position = 'footer', showBuildInfo = false }) {
  const [buildInfo, setBuildInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Frontend version from package.json or build constant
  const FRONTEND_VERSION = process.env.REACT_APP_VERSION || 
                           process.env.REACT_APP_GIT_SHA ||
                           'dev';
  
  // Check if build badge should be shown
  const shouldShowBadge = showBuildInfo || 
                          process.env.REACT_APP_SHOW_BUILD_BADGE === 'true';
  
  useEffect(() => {
    if (shouldShowBadge) {
      fetchBuildInfo();
    } else {
      setLoading(false);
    }
  }, [shouldShowBadge]);
  
  const fetchBuildInfo = async () => {
    try {
      const response = await fetch(`${API_BASE}/build/info`);
      if (response.ok) {
        const data = await response.json();
        setBuildInfo(data);
      } else {
        setError('Could not fetch build info');
      }
    } catch (err) {
      console.warn('Version badge: could not fetch build info', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  // Don't show badge if not enabled
  if (!shouldShowBadge) {
    return null;
  }
  
  if (loading) {
    return null; // Don't show anything while loading
  }
  
  if (error || !buildInfo) {
    // Show frontend version only if backend unavailable
    return (
      <div className={`version-badge ${position}`}>
        <Badge variant="outline" className="text-xs">
          v{FRONTEND_VERSION.substring(0, 8)}
        </Badge>
      </div>
    );
  }
  
  const backendVersion = buildInfo.version?.substring(0, 8) || 'unknown';
  const environment = buildInfo.env || 'dev';
  const versionsMatch = FRONTEND_VERSION.startsWith(backendVersion) || 
                        backendVersion.startsWith(FRONTEND_VERSION);
  
  return (
    <div className={`version-badge ${position}`}>
      <div className="flex items-center gap-2 text-xs">
        <Badge 
          variant={versionsMatch ? "default" : "destructive"}
          className="text-xs"
        >
          {environment === 'production' ? '🚀' : '🔧'} {backendVersion}
        </Badge>
        
        {!versionsMatch && (
          <Badge variant="outline" className="text-xs opacity-60">
            FE: {FRONTEND_VERSION.substring(0, 8)}
          </Badge>
        )}
      </div>
    </div>
  );
}
