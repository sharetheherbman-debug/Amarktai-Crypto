import React from 'react';
import SiteFooter from './SiteFooter';
import NeuralBackground from './NeuralBackground';
import './AuthLayout.css';

/**
 * Shared layout component for Landing, Login, and Register pages
 * Features:
 * - Full-page neural-network background
 * - Centred content panel with glass overlay
 */
export default function AuthLayout({ children }) {
  return (
    <div className="auth-container">
      {/* Neural network background layer */}
      <NeuralBackground />

      {/* Content */}
      <div className="auth-left">
        {children}
      </div>

      {/* Footer */}
      <SiteFooter />
    </div>
  );
}

