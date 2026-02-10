import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../lib/api.js';
import { formatTimestamp } from '../lib/dateUtils.js';

const API = API_BASE;

/**
 * Normalize live price responses into a pair->price map.
 *
 * Accepts either array responses from /api/prices/live or
 * object maps already keyed by pair. Returns fallback if the
 * response is empty or invalid.
 */
export const normalizeLivePrices = (data, fallback = null) => {
  if (Array.isArray(data)) {
    const pricesMap = {};
    data.forEach((price) => {
      if (!price?.pair) return;
      pricesMap[price.pair] = {
        price: price.price || 0,
        change: price.change_24h || 0,
        last_update: price.last_update,
        source: price.source
      };
    });
    if (Object.keys(pricesMap).length > 0) {
      return pricesMap;
    }
  } else if (data && typeof data === 'object') {
    const entries = Object.values(data);
    if (entries.length > 0 && entries.some(entry => entry && typeof entry === 'object')) {
      return data;
    }
  }

  return fallback;
};

/**
 * Custom hook for managing dashboard data fetching and state
 */
export const useDashboardData = (token) => {
  const [user, setUser] = useState(null);
  const [bots, setBots] = useState([]);
  const [metrics, setMetrics] = useState({
    totalProfit: 'R0.00',
    activeBots: '0 / 0',
    exposure: '0%',
    riskLevel: 'Unknown',
    aiSentiment: 'Neutral',
    lastUpdate: '—'
  });
  const [systemModes, setSystemModes] = useState({
    paperTrading: false,
    liveTrading: false,
    autopilot: false
  });
  const [apiKeys, setApiKeys] = useState({});
  const [recentTrades, setRecentTrades] = useState([]);
  const [countdown, setCountdown] = useState(null);
  const [livePrices, setLivePrices] = useState({
    'BTC/ZAR': { price: 0, change: 0 },
    'ETH/ZAR': { price: 0, change: 0 },
    'XRP/ZAR': { price: 0, change: 0 }
  });
  const [profitData, setProfitData] = useState(null);

  const axiosConfig = { headers: { Authorization: `Bearer ${token}` } };

  const loadUser = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/auth/me`, axiosConfig);
      setUser(res.data);
    } catch (err) {
      console.error('User fetch error:', err);
    }
  }, [token]);

  const loadBots = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/bots/status`, axiosConfig);
      const botsData = res.data?.bots || res.data || [];
      setBots(botsData);
    } catch (err) {
      console.error('Bots fetch error:', err);
    }
  }, [token]);

  const loadMetrics = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/overview`, axiosConfig);
      setMetrics({
        totalProfit: `R${res.data.total_profit?.toFixed(2) || '0.00'}`,
        activeBots: res.data.activeBots || '0 / 0',
        exposure: `${res.data.exposure?.toFixed(2) || '0'}%`,
        riskLevel: res.data.risk_level || 'Unknown',
        aiSentiment: res.data.ai_sentiment || 'Neutral',
        lastUpdate: formatTimestamp(new Date(), { includeDate: false })
      });
    } catch (err) {
      console.error('Metrics fetch error:', err);
    }
  }, [token]);

  const loadSystemModes = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/system/mode`, axiosConfig);
      setSystemModes({
        paperTrading: res.data.paperTrading || false,
        liveTrading: res.data.liveTrading || false,
        autopilot: res.data.autopilot || false
      });
    } catch (err) {
      console.error('System modes fetch error:', err);
    }
  }, [token]);

  const loadApiStatuses = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/keys/status`, axiosConfig);
      const statusMap = res.data?.status_map || {};
      setApiKeys(statusMap);
    } catch (err) {
      console.error('API keys fetch error:', err);
    }
  }, [token]);

  const loadRecentTrades = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/trades/recent?limit=50`, axiosConfig);
      setRecentTrades(res.data.trades || []);
    } catch (err) {
      console.error('Recent trades fetch error:', err);
    }
  }, [token]);

  const loadCountdown = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/analytics/countdown-to-million`, axiosConfig);
      setCountdown(res.data);
    } catch (err) {
      console.error('Countdown fetch error:', err);
    }
  }, [token]);

  const loadLivePrices = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/prices/live`, axiosConfig);
      setLivePrices(prev => normalizeLivePrices(res.data, prev));
    } catch (err) {
      console.error('Live prices fetch error:', err);
    }
  }, [token]);

  const loadProfitData = useCallback(async (period = 'daily') => {
    try {
      const res = await axios.get(`${API}/analytics/profit-history?period=${period}`, axiosConfig);
      setProfitData(res.data);
    } catch (err) {
      console.error('Profit data fetch error:', err);
    }
  }, [token]);

  const refreshAll = useCallback(() => {
    loadBots();
    loadMetrics();
    loadSystemModes();
    loadRecentTrades();
    loadCountdown();
    loadLivePrices();
  }, [loadBots, loadMetrics, loadSystemModes, loadRecentTrades, loadCountdown, loadLivePrices]);

  return {
    user,
    bots,
    metrics,
    systemModes,
    apiKeys,
    recentTrades,
    countdown,
    livePrices,
    profitData,
    setUser,
    setBots,
    setMetrics,
    setSystemModes,
    setApiKeys,
    setRecentTrades,
    setCountdown,
    setLivePrices,
    setProfitData,
    loadUser,
    loadBots,
    loadMetrics,
    loadSystemModes,
    loadApiStatuses,
    loadRecentTrades,
    loadCountdown,
    loadLivePrices,
    loadProfitData,
    refreshAll
  };
};
