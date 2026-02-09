import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../lib/api.js';
import { formatTimestamp } from '../lib/dateUtils.js';

const API = API_BASE;

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
      const res = await axios.get(`${API}/bots`, axiosConfig);
      setBots(res.data || []);
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
      const res = await axios.get(`${API}/keys/list`, axiosConfig);
      const keysMap = {};
      // New API returns { success: true, keys: [...] }
      const keys = res.data?.keys || res.data || [];
      keys.forEach(key => {
        keysMap[key.provider] = key;
      });
      setApiKeys(keysMap);
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
      if (res.data && Array.isArray(res.data)) {
        const pricesMap = {};
        res.data.forEach(p => {
          pricesMap[p.pair] = {
            price: p.price || 0,
            change: p.change_24h || 0
          };
        });
        setLivePrices(pricesMap);
      }
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
