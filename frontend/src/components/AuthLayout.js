import React from 'react';
import SiteFooter from './SiteFooter';
import './AuthLayout.css';

/**
 * Shared layout component for Landing, Login, and Register pages
 * Features:
 * - LEFT PANEL (50%): Two blue colors blended at 135° diagonal gradient
 * - RIGHT PANEL (50%): Video background
 * - Responsive: Mobile shows video as background with dark overlay
 */
export default function AuthLayout({ children, videoRotated = false }) {
  return (
    <div className="auth-container">
      {/* Left Column - Content with diagonal blue gradient */}
      <div className="auth-left">
        {children}
      </div>

      {/* Right Column - Video */}
      <div className={`auth-right ${videoRotated ? 'auth-right-rotated' : ''}`}>
        <video
          autoPlay
          muted
          loop
          playsInline
          poster="/assets/poster.jpg"
        >
          <source src="/assets/background.mp4" type="video/mp4" />
        </video>
        <div className="auth-overlay" />
      </div>

      {/* Footer */}
      <SiteFooter />
    </div>
  );
}
