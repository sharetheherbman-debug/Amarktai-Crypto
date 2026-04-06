import React from 'react';
import SiteFooter from './SiteFooter';
import ParticleBackground from './ParticleBackground';
import './AuthLayout.css';

/**
 * Shared layout component for Landing, Login, and Register pages
 * Features:
 * - Full-page particle background (red/green/yellow)
 * - Centred content panel with glass overlay
 */
export default function AuthLayout({ children }) {
  return (
    <div className="auth-container">
      {/* Particle background layer */}
      <ParticleBackground />

      {/* Content */}
      <div className="auth-left">
        {children}
      </div>

      {/* Footer */}
      <SiteFooter />
    </div>
  );
}

