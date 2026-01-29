import { useState, useEffect } from 'react';
import { Badge } from './ui/badge';
import { API_BASE } from '../lib/api';

/**
 * VersionBadge Component
 * 
 * Displays the current build version of frontend and backend.
 * Fetches version info from /api/build/info endpoint (no auth required).
 * Shows in footer or header to verify deployment.
 */
export default function VersionBadge({ position = 'footer' }) {
  const [buildInfo, setBuildInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Frontend version from package.json or build constant
  const FRONTEND_VERSION = process.env.REACT_APP_VERSION || 
                           process.env.REACT_APP_GIT_SHA ||
                           'dev';
  
  useEffect(() => {
    fetchBuildInfo();
  }, []);
  
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
        
        {buildInfo.built_at && (
          <span className="text-xs opacity-50" title={buildInfo.built_at}>
            {new Date(buildInfo.built_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}
