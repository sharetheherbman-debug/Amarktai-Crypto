/**
 * Dashboard cleanup tests
 *
 * Validates:
 * 1. Analytics & Intelligence nav is removed
 * 2. Bot Operations replaces separate bot entries
 * 3. Nav labels are correct
 * 4. No duplicate user management
 * 5. Public routes are isolated from dashboard logic
 */

import { NAV, NAV_LABELS } from '../constants/dashboardNav';

/* ── 1. Analytics section removed ────────────────────────── */
test('Analytics nav entry is removed from dashboard navigation', () => {
  // NAV.ANALYTICS_METRICS should alias to profits-performance (no separate section)
  expect(NAV.ANALYTICS_METRICS).toBe('profits-performance');
  // NAV_LABELS should not have any Analytics & Intelligence key
  const labels = Object.values(NAV_LABELS);
  const hasAnalytics = labels.some(l => /analytics.*intelligence/i.test(l));
  expect(hasAnalytics).toBe(false);
});

/* ── 2. Bot Operations consolidation ──────────────────────── */
test('Bot sections are consolidated into single Bot Operations nav entry', () => {
  expect(NAV.BOT_OPS).toBe('bot-ops');
  expect(NAV_LABELS[NAV.BOT_OPS]).toBe('🚀 Bot Operations');

  // Legacy aliases should point to bot-ops
  expect(NAV.BOT_MANAGEMENT).toBe('bot-ops');
  expect(NAV.BOT_FLEET).toBe('bot-ops');
  expect(NAV.BOT_RADAR).toBe('bot-ops');
});

/* ── 3. Nav labels are clean ──────────────────────────────── */
test('Dashboard nav has correct number of entries (no duplicates)', () => {
  const uniqueLabels = new Set(Object.values(NAV_LABELS));
  // 11 unique labels: Welcome, API Setup, Bot Operations, Growth Engine, System Mode,
  // Profits & Performance, Live Trades, Countdown, Wallet Hub, Profile, Admin
  expect(uniqueLabels.size).toBe(11);
});

test('No duplicate nav labels exist', () => {
  const labels = Object.values(NAV_LABELS);
  const seen = new Set();
  for (const label of labels) {
    expect(seen.has(label)).toBe(false);
    seen.add(label);
  }
});

/* ── 4. Auth isolation ─────────────────────────────────────── */
test('Login page does not import dashboard hooks', () => {
  const loginSource = require('fs').readFileSync(
    require('path').resolve(__dirname, '../pages/Login.js'), 'utf8'
  );
  expect(loginSource).not.toContain('useDashboardState');
  expect(loginSource).not.toContain('useDashboardData');
  expect(loginSource).not.toContain('realtimeClient');
  expect(loginSource).not.toContain('useRealtime');
});

test('Register page does not import dashboard hooks', () => {
  const regSource = require('fs').readFileSync(
    require('path').resolve(__dirname, '../pages/Register.js'), 'utf8'
  );
  expect(regSource).not.toContain('useDashboardState');
  expect(regSource).not.toContain('useDashboardData');
  expect(regSource).not.toContain('realtimeClient');
});

test('Landing page does not import dashboard hooks', () => {
  const landingSource = require('fs').readFileSync(
    require('path').resolve(__dirname, '../pages/Landing.js'), 'utf8'
  );
  expect(landingSource).not.toContain('useDashboardState');
  expect(landingSource).not.toContain('useDashboardData');
  expect(landingSource).not.toContain('realtimeClient');
});

/* ── 5. Realtime client has auth guard ─────────────────────── */
test('Realtime client guards reconnect when logged out', () => {
  const rtSource = require('fs').readFileSync(
    require('path').resolve(__dirname, '../lib/realtime.js'), 'utf8'
  );
  // Must check for token before reconnecting
  expect(rtSource).toContain('if (!this.token)');
  // Must set onclose to null on disconnect to prevent reconnect storms
  expect(rtSource).toContain('this.ws.onclose = null');
});

/* ── 6. apiClient suppresses 401 on public routes ──────────── */
test('apiClient handles 401 differently on public routes', () => {
  const apiSource = require('fs').readFileSync(
    require('path').resolve(__dirname, '../lib/apiClient.js'), 'utf8'
  );
  expect(apiSource).toContain('isPublicRoute');
  expect(apiSource).toContain('/login');
  expect(apiSource).toContain('/register');
});
