import React from 'react';
import SiteFooter from './SiteFooter';
import './AuthLayout.css';

/**
 * Shared layout component for Landing, Login, and Register pages
 * Features:
 * - LEFT PANEL (50%): Gradient content area
 * - RIGHT PANEL (50%): Flat dark placeholder (media removed for stability)
 * - Responsive: Mobile shows dark background with dark overlay
 */
export default function AuthLayout({ children, videoRotated = false }) {
  return (
    <div className="auth-container">
      {/* Left Column - Content with diagonal blue gradient */}
      <div className="auth-left">
        {children}
      </div>

      {/* Right Column - Flat dark placeholder (no video) */}
      <div className="auth-right auth-right-placeholder" />

      {/* Footer */}
      <SiteFooter />
    </div>
  );
}

