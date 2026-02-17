import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import { useDashboardData, normalizeLivePrices, getBotStatus } from './useDashboardData';
import apiClient, { post, get, notifyError } from '../lib/apiClient';
import realtimeClient from '../lib/realtime';
import { wsUrl } from '../lib/api.js';
import { formatTimestamp } from '../utils/time.js';
import { useRealtimeEvent } from './useRealtime';
import { getAllExchanges, getActiveExchanges, getExchangeById, FEATURE_FLAGS } from '../config/exchanges';
import { SUPPORTED_PLATFORMS, PLATFORM_CONFIG, getPlatformDisplayName, getPlatformIcon } from '../constants/platforms';

const API = '';
const axios = apiClient;
const APP_VERSION = '1.0.6';
const NOT_AVAILABLE = 'Not available';

const EXCHANGES_NEEDING_SECRET = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];
const EXCHANGES_NEEDING_PASSPHRASE = ['kucoin', 'bitget'];

const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const resolveSystemMode = (modeRes) => {
  if (!modeRes) return 'paper';
  return modeRes.mode || (modeRes.liveTrading ? 'live' : modeRes.autopilot ? 'autopilot' : 'paper');
};

const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

const safePercent = (value, digits = 1, fallback = '0.0') => `${safeToFixed(value, digits, fallback)}%`;

const formatCurrencyValue = (value, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return num.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
};

const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

const toTitleCase = (value) => value.replace(/\w\S*/g, (word) =>
  word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
);

const humanizeReason = (reason) => {
  if (!reason) return NOT_AVAILABLE;
  const raw = String(reason).trim();
  if (!raw || raw === '-' || raw === '--') return NOT_AVAILABLE;
  const normalizedCode = raw.replace(/[-\s]+/g, '_').replace(/_+/g, '_').toUpperCase();
  if (SPAWN_REASON_LABELS[normalizedCode]) {
    return SPAWN_REASON_LABELS[normalizedCode];
  }
  if (!/[_-]/.test(raw) && /[a-z]/.test(raw)) {
    return raw;
  }
  return toTitleCase(raw.replace(/[-_]+/g, ' ').toLowerCase());
};

const SPAWN_REASON_LABELS = {
  PROFIT_TOO_LOW: 'Profit too low',
  NOT_READY: 'Not ready',
  COOLDOWN_ACTIVE: 'Cooldown active',
  MAX_SPAWNS_REACHED: 'Daily limit reached',
  INSUFFICIENT_BALANCE: 'Insufficient balance',
  NOT_ENABLED: 'Not enabled',
  ELIGIBLE: 'Eligible'
};

const formatSpawnReason = (reason) => {
  if (!reason) {
    return { title: NOT_AVAILABLE, details: '' };
  }
  const raw = String(reason).trim();
  const [codePart, detailPart] = raw.split('(');
  const title = humanizeReason(codePart);
  let details = detailPart ? detailPart.replace(')', '').trim() : '';
  if (details) {
    const detailsParts = [];
    const pattern = /\b(need|have)\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)/gi;
    let match;
    while ((match = pattern.exec(details)) !== null) {
      const label = match[1].toLowerCase() === 'need' ? 'Need' : 'Currently';
      const amount = match[2];
      const currencyCode = match[3].toUpperCase();
      const formattedAmount = currencyCode === 'ZAR'
        ? formatZAR(amount)
        : `${formatCurrencyValue(amount) ?? amount} ${currencyCode}`;
      detailsParts.push(`${label} ${formattedAmount}`);
    }
    if (detailsParts.length) {
      details = detailsParts.join(', ');
    } else {
      details = toTitleCase(details.replace(/[-_]+/g, ' ').toLowerCase());
    }
  }
  return { title, details };
};

const formatReasonInline = (reason) => {
  const info = formatSpawnReason(reason);
  if (!info.details) return info.title;
  return `${info.title} — ${info.details}`;
};

export default function useDashboardState(navigate) {
  const [user, setUser] = useState(null);
  const [activeSection, setActiveSection] = useState('welcome');
  const [intelligenceTab, setIntelligenceTab] = useState('whale-flow'); // Tab state for Intelligence section
  const [metricsTab, setMetricsTab] = useState('flokx'); // Tab state for Metrics section - default to Flokx Alerts
  const [botManagementTab, setBotManagementTab] = useState('creation'); // Tab state for Bot Management parent section
  const [profitsTab, setProfitsTab] = useState('metrics'); // Tab state for Profits & Performance parent section
  const [botStatusFilter, setBotStatusFilter] = useState('all');
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(false);
  // Admin panel state - Hidden by default each session, only shown after password unlock
  // Do NOT persist across sessions - user must unlock each time
  const [showAdmin, setShowAdmin] = useState(false);
  
  // Log whenever showAdmin changes
  useEffect(() => {
    console.log('🔄 showAdmin state changed to:', showAdmin);
  }, [showAdmin]);
  useEffect(() => {
    if (user?.risk_profile) {
      setRiskProfile(user.risk_profile);
    }
  }, [user]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [bots, setBots] = useState([]);
  const [apiKeys, setApiKeys] = useState({});
  const [metrics, setMetrics] = useState({
    totalProfit: 'R0.00',
    activeBots: '0 / 0',
    exposure: '0%',
    riskLevel: NOT_AVAILABLE,
    aiSentiment: NOT_AVAILABLE,
    lastUpdate: NOT_AVAILABLE
  });
  const [balances, setBalances] = useState({ zar: 0, btc: 0 });
  const [systemModes, setSystemModes] = useState({
    paperTrading: false,
    liveTrading: false,
    autopilot: false
  });
  const [awaitingPassword, setAwaitingPassword] = useState(false);
  const [adminAction, setAdminAction] = useState(null);
  const [isMobile, setIsMobile] = useState(false);
  const [selectedBotDetailId, setSelectedBotDetailId] = useState(null);
  const [botDetailTab, setBotDetailTab] = useState('overview');
  const [selectedTradeId, setSelectedTradeId] = useState(null);
  const [tradeExchangeFilter, setTradeExchangeFilter] = useState('all');
  const [tradeBotFilter, setTradeBotFilter] = useState('all');
  const [tradePairFilter, setTradePairFilter] = useState('all');
  const [expandedApis, setExpandedApis] = useState({});
  const [activeBotTab, setActiveBotTab] = useState('exchange'); // Setup wizard removed - users create starting bots manually
  const [graphPeriod, setGraphPeriod] = useState('daily');
  const [profitData, setProfitData] = useState(null);
  const [equityData, setEquityData] = useState(null);
  const [drawdownData, setDrawdownData] = useState(null);
  const [winRateData, setWinRateData] = useState(null);
  const [equityRange, setEquityRange] = useState('7d');
  const [drawdownRange, setDrawdownRange] = useState('7d');
  const [winRatePeriod, setWinRatePeriod] = useState('all');
  const [projection, setProjection] = useState(null);
  const [depositAddress, setDepositAddress] = useState(null);
  const [profileData, setProfileData] = useState({});
  const [allUsers, setAllUsers] = useState([]);
  const [systemStats, setSystemStats] = useState(null);
  const [flokxAlerts, setFlokxAlerts] = useState([]);
  const [isFlokxActive, setIsFlokxActive] = useState(false);
  const [flokxStatus, setFlokxStatus] = useState({ configured: false, last_error: null, last_tested_at: null });
  const [connectionStatus, setConnectionStatus] = useState({
    api: 'Disconnected',
    sse: 'Disconnected',
    ws: 'Disconnected'
  });
  const [wsRtt, setWsRtt] = useState(NOT_AVAILABLE);
  const [sseLastUpdate, setSseLastUpdate] = useState(null); // Track SSE last update time
  const [platformFilter, setPlatformFilter] = useState('all');
  const [editingBotId, setEditingBotId] = useState(null);
  const [editingBotName, setEditingBotName] = useState('');
  const [metricsExpanded, setMetricsExpanded] = useState(false); // State for metrics submenu
  const [botSetup, setBotSetup] = useState({
    count: 10,
    capital_per_bot: 1000,
    safe_count: 6,
    risky_count: 2,
    aggressive_count: 2,
    exchange: 'luno'
  });
  const [systemHealth, setSystemHealth] = useState({
    status: NOT_AVAILABLE,
    errors: 0,
    uptime: NOT_AVAILABLE,
    lastCheck: NOT_AVAILABLE
  });
  const [overviewData, setOverviewData] = useState({
    totalProfit: 0,
    todaysTrades: 0,
    openPositions: 0,
    winRate: 0,
    activeBots: 0,
    paperWalletTotal: 0,
    paperWalletAllocated: 0,
    lastTradeTime: null,
    systemMode: 'paper',
    lastRebalance: 'Not available',
    nextReinvest: 'Not available'
  });
  const [botControlLoading, setBotControlLoading] = useState({});
  const [recentTrades, setRecentTrades] = useState([]);
  const [bodyguardStatus, setBodyguardStatus] = useState(null);
  // Consolidated risk status from /api/risk/status
  const [riskStatus, setRiskStatus] = useState(null);
  const [autonomyStatus, setAutonomyStatus] = useState(null);
  const [aiStatus, setAiStatus] = useState(null);
  const [learningStatus, setLearningStatus] = useState(null);
  const [riskProfile, setRiskProfile] = useState('balanced');
  const [autoSpawnStatus, setAutoSpawnStatus] = useState(null);
  const [autopilotGrowthStatus, setAutopilotGrowthStatus] = useState(null);
  const [autopilotReinvestStatus, setAutopilotReinvestStatus] = useState(null);
  const [realtimeFallback, setRealtimeFallback] = useState(false);
  const [storageData, setStorageData] = useState(null);
  const [storageError, setStorageError] = useState(null);
  const [countdown, setCountdown] = useState(null);
  const [customCountdowns, setCustomCountdowns] = useState([]);
  const [showAddCountdown, setShowAddCountdown] = useState(false);
  const [newCountdownLabel, setNewCountdownLabel] = useState('');
  const [newCountdownAmount, setNewCountdownAmount] = useState('');
  const [aiTaskLoading, setAiTaskLoading] = useState(null); // Track which AI task is running
  const [showAITools, setShowAITools] = useState(false); // Toggle AI tools submenu
  const [eligibleBots, setEligibleBots] = useState([]);
  const [showPromotionModal, setShowPromotionModal] = useState(false);
  const [paperResetError, setPaperResetError] = useState('');
  const [paperResetLoading, setPaperResetLoading] = useState(false);
  const [showPaperResetModal, setShowPaperResetModal] = useState(false);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminBots, setAdminBots] = useState([]);
  const [adminApiHealth, setAdminApiHealth] = useState({ status: 'Unknown', lastCheck: null, error: null });
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingBots, setLoadingBots] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedBotId, setSelectedBotId] = useState('');
  const [filteredAdminBots, setFilteredAdminBots] = useState([]);
  const [emergencyOverrideStatus, setEmergencyOverrideStatus] = useState(null);
  
  const chatEndRef = useRef(null);
  const wsRef = useRef(null);
  const sseRef = useRef(null);
  const botStatusErrorRef = useRef({ lastShown: 0 });
  
  const token = localStorage.getItem('token');
  const axiosConfig = useMemo(() => ({
    headers: { Authorization: `Bearer ${token}` }
  }), [token]);
  const { livePrices, loadLivePrices, setLivePrices } = useDashboardData(token);
  const storageTotals = useMemo(() => {
    if (!storageData) {
      return null;
    }
    const totalMb = storageData.total_system_storage_mb ?? storageData.total_storage_mb ?? 0;
    return {
      totalMb,
      totalGb: totalMb / 1024,
      totalUsers: storageData.total_users ?? storageData.user_count ?? 0
    };
  }, [storageData]);

  // Safe date formatter - handles null/undefined gracefully
  const formatDate = (dateStr, options = {}) => {
    if (!dateStr) return NOT_AVAILABLE;
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return NOT_AVAILABLE;
      
      const { format = 'localeString' } = options;
      switch (format) {
        case 'localeString':
          return date.toLocaleString();
        case 'localeDateString':
          return date.toLocaleDateString();
        case 'localeTimeString':
          return date.toLocaleTimeString();
        default:
          return date.toLocaleString();
      }
    } catch (error) {
      console.error('Date format error:', error);
      return NOT_AVAILABLE;
    }
  };

  const formatDuration = (seconds) => {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return NOT_AVAILABLE;
    const totalSeconds = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  };

  const formatActionError = (err, fallbackMessage) => {
    const detail = err?.response?.data?.detail;
    if (detail && typeof detail === 'object') {
      const parts = [detail.message || detail.error || fallbackMessage];
      if (detail.next_action) {
        parts.push(`Next: ${detail.next_action}`);
      }
      if (detail.remaining_seconds !== undefined && detail.remaining_seconds !== null) {
        parts.push(`Wait ${formatDuration(detail.remaining_seconds)}`);
      }
      if (detail.release_at) {
        parts.push(`Release: ${formatDate(detail.release_at)}`);
      }
      return parts.filter(Boolean).join(' • ');
    }
    return detail || err?.message || fallbackMessage;
  };

  // Track if WebSocket has been initialized to prevent double initialization
  const wsInitializedRef = useRef(false);

  useEffect(() => {
    if (!token) {
      navigate('/login');
      return;
    }
    loadUser();
    loadBots();
    loadMetrics();
    loadSystemModes();
    loadApiStatuses();
    loadRecentTrades();
    loadCountdown();
    loadCustomCountdowns();
    loadSystemHealth();
    loadOverviewData();
    loadRiskStatus();
    
    // Setup real-time connections ONCE
    if (!wsInitializedRef.current) {
      setupRealTimeConnections();
      wsInitializedRef.current = true;
    }
    
    // Handle responsive
    const handleResize = () => setIsMobile(window.innerWidth <= 900);
    handleResize();
    window.addEventListener('resize', handleResize);
    
    // Listen for navigation events from components
    const handleNavigateToSection = (e) => {
      if (e.detail && e.detail.section) {
        showSection(e.detail.section);
      }
    };
    window.addEventListener('navigateToSection', handleNavigateToSection);
    
    // Add personalized welcome message
    setChatMessages([{
      role: 'assist',
      content: `Hello ${user?.first_name || 'there'}! Welcome to Amarktai Crypto. I'm your AI assistant with full control over your trading system. Try commands like 'create a bot', 'show performance', 'enable autopilot', or ask me anything about your trading!`
    }]);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('navigateToSection', handleNavigateToSection);
      if (wsRef.current) {
        wsRef.current.close();
        wsInitializedRef.current = false;
      }
      if (sseRef.current) sseRef.current.close();
    };
  }, []);
  
  useEffect(() => {
    if (token && user) {
      refreshAllDashboardData();
      loadSystemStats();
      loadProfitData();
      // REMOVED: Duplicate setupRealTimeConnections() call

      let priceInterval;
      const startPolling = () => {
        loadLivePrices();
        priceInterval = setInterval(loadLivePrices, 4000);
      };

      const stopPolling = () => {
        if (priceInterval) {
          clearInterval(priceInterval);
        }
      };

      const handleVisibility = () => {
        if (document.hidden) {
          stopPolling();
        } else {
          startPolling();
        }
      };

      startPolling();
      document.addEventListener('visibilitychange', handleVisibility);

      return () => {
        stopPolling();
        document.removeEventListener('visibilitychange', handleVisibility);
        // Don't close WebSocket here, it's managed by the first useEffect
      };
    }
  }, [token, user]);

  // Poll overview and risk data every 10 seconds
  useEffect(() => {
    if (!token || !user) return;
    
    const interval = setInterval(() => {
      loadOverviewData();
      loadRiskStatus();
      if (realtimeFallback) {
        loadSystemHealth();
        loadCountdown();
        loadSystemStats();
      }
    }, 10000);
    
    return () => clearInterval(interval);
  }, [token, user, realtimeFallback]);

  useEffect(() => {
    if (!token) return;
    let mounted = true;
    const checkRealtimeStatus = async () => {
      try {
        const res = await get('/diagnostics/realtime');
        if (!mounted) return;
        setRealtimeFallback(safeNumber(res?.ws_connected, 0) === 0);
      } catch (err) {
        if (mounted) {
          setRealtimeFallback(true);
        }
      }
    };
    checkRealtimeStatus();
    const interval = setInterval(checkRealtimeStatus, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Load profit data when period changes
  useEffect(() => {
    if (connectionStatus.sse === 'Connected' || connectionStatus.api === 'Connected') {
      loadProfitData();
    }
  }, [graphPeriod, connectionStatus]);

  useEffect(() => {
    setSelectedTradeId(null);
  }, [tradeExchangeFilter, tradeBotFilter, tradePairFilter]);

  // Load equity data when equity tab is active or range changes
  useEffect(() => {
    if (user && profitsTab === 'equity') {
      loadEquityData();
    }
  }, [equityRange, profitsTab, user]);

  // Load drawdown data when drawdown tab is active or range changes
  useEffect(() => {
    if (user && profitsTab === 'drawdown') {
      loadDrawdownData();
    }
  }, [drawdownRange, profitsTab, user]);

  // Load win rate data when win-rate tab is active or period changes
  useEffect(() => {
    if (user && profitsTab === 'win-rate') {
      loadWinRateData();
    }
  }, [winRatePeriod, profitsTab, user]);

  // Load projection for countdown
  useEffect(() => {
    calculateProjection();
    const interval = setInterval(calculateProjection, 60000);
    return () => clearInterval(interval);
  }, [balances, metrics]);

  // Load deposit address
  useEffect(() => {
    loadDepositAddress();
  }, []);

  // Set profile data when user loads
  useEffect(() => {
    if (user) {
      setProfileData({
        first_name: user.first_name || '',
        email: user.email || '',
        currency: user.currency || 'ZAR',
        new_password: ''
      });
    }
  }, [user]);

  // PHASE 12: Load chat history from backend (30 days) - DISABLED BY DEFAULT
  // Chat history is NOT auto-loaded; user must click "Load History" button
  // Default behavior: show fresh greeting only
  useEffect(() => {
    // Initialize with welcome message (no auto-load of history)
    if (user && chatMessages.length === 0) {
      setChatMessages([{
        role: 'assistant',
        content: `Hello ${user.first_name || 'there'}! Welcome to Amarktai Crypto. I'm your AI assistant. Try commands like 'show admin', 'help', or ask me anything!`
      }]);
    }
  }, [user]);

  const loadChatHistory = async () => {
    try {
      // Load chat history from backend (per-user, auto-namespaced by JWT)
      const data = await get('/chat/history?days=30&limit=100');
      if (data.messages && data.messages.length > 0) {
        // Messages are already in chronological order (newest-last) from backend
        setChatMessages(data.messages);
      } else {
        // Initialize with welcome message if no history
        if (user) {
          setChatMessages([{
            role: 'assistant',
            content: `Hello ${user.first_name || 'there'}! Welcome to Amarktai Crypto. I'm your AI assistant. Try commands like 'show admin', 'help', or ask me anything!`
          }]);
        }
      }
    } catch (error) {
      console.error('Failed to load chat history:', error);
      // Show empty state without flooding console with errors
      if (user) {
        setChatMessages([{
          role: 'assistant',
          content: `Hello ${user.first_name || 'there'}! Welcome to Amarktai Crypto. I'm your AI assistant. Try commands like 'show admin', 'help', or ask me anything!`
        }]);
      }
    }
  };

  const handleClearChatHistory = async () => {
    if (!window.confirm('Clear all chat history? This action cannot be undone.')) {
      return;
    }
    
    try {
      await post('/chat/clear', { clear_server_side: true });
      // Reset to fresh greeting
      if (user) {
        setChatMessages([{
          role: 'assistant',
          content: `Hello ${user.first_name || 'there'}! Welcome to Amarktai Crypto. I'm your AI assistant. Try commands like 'show admin', 'help', or ask me anything!`
        }]);
      }
      showNotification('Chat history cleared successfully', 'success');
    } catch (error) {
      console.error('Failed to clear chat history:', error);
      showNotification('Failed to clear chat history', 'error');
    }
  };

  // PHASE 10: Subscribe to real-time AI task updates
  useRealtimeEvent('ai_tasks', useCallback((task) => {
    console.log('AI Task update:', task);
    
    if (task.status === 'completed') {
      setAiTaskLoading(null);
      toast.success(`${task.task_type} completed successfully`);
      
      // Refresh data based on task type
      if (task.task_type === 'bot_evolution') {
        loadBots();
      } else if (task.task_type === 'profit_reinvestment') {
        loadMetrics();
        loadBalances();
      }
    } else if (task.status === 'failed') {
      setAiTaskLoading(null);
      toast.error(`${task.task_type} failed: ${task.error || 'Unknown error'}`);
    } else if (task.status === 'running') {
      toast.info(`${task.task_type} in progress: ${Math.round(task.progress * 100)}%`);
    }
  }, []), []);

  // Check for eligible bots every 5 minutes
  useEffect(() => {
    checkEligibleBots();
    const interval = setInterval(checkEligibleBots, 300000); // 5 minutes
    return () => clearInterval(interval);
  }, []);

  const refreshBotState = async () => {
    await Promise.all([
      loadBots(),
      loadOverviewData(),
      loadAutoSpawnStatus(),
      loadAutopilotGrowthStatus(),
      loadAutopilotReinvestStatus()
    ]);
    if (showAdmin) {
      await Promise.all([loadAdminBots(), loadAdminUsers(), loadSystemStats()]);
    }
  };

  const refreshAllDashboardData = async () => {
    await Promise.all([
      loadBots(),
      loadMetrics(),
      loadSystemModes(),
      loadApiStatuses(),
      loadRecentTrades(),
      loadCountdown(),
      loadLivePrices(),
      loadOverviewData(),
      loadRiskStatus(),
      loadSystemHealth(),
      loadAutoSpawnStatus(),
      loadAutopilotGrowthStatus(),
      loadAutopilotReinvestStatus()
    ]);
  };

  const isPaperResetMode = systemModes.paperTrading && !systemModes.liveTrading;

  useEffect(() => {
    if (!isPaperResetMode) {
      setPaperResetError('');
      setShowPaperResetModal(false);
    }
  }, [isPaperResetMode]);

  useEffect(() => {
    if (!token) return undefined;
    loadLivePrices();
    const priceInterval = setInterval(loadLivePrices, 5000);
    return () => clearInterval(priceInterval);
  }, [token, loadLivePrices]);

  // Update filtered bots when adminBots or selectedUserId changes
  useEffect(() => {
    if (selectedUserId && adminBots.length > 0) {
      const userBots = adminBots.filter(bot => bot.user_id === selectedUserId);
      setFilteredAdminBots(userBots);
    } else {
      setFilteredAdminBots([]);
    }
  }, [adminBots, selectedUserId]);

  // Check Flokx status
  useEffect(() => {
    if (!token) return undefined;
    loadFlokxStatus();
    const interval = setInterval(loadFlokxStatus, 30000);
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    if (isFlokxActive) {
      loadFlokxAlerts();
      const interval = setInterval(loadFlokxAlerts, 30000);
      return () => clearInterval(interval);
    }
    setFlokxAlerts([]);
    return undefined;
  }, [isFlokxActive]);

  const setupRealTimeConnections = () => {
    console.log('✅ Initializing WebSocket connection...');
    
    // Also connect the realtime client for API key events
    if (token) {
      realtimeClient.connect(token);
    }
    
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;
    
    const connectWebSocket = () => {
      try {
        // Use shared helper to build same-origin WS URL (wss:// on HTTPS)
        const wsEndpoint = `${wsUrl()}?token=${token}`;
        wsRef.current = new WebSocket(wsEndpoint);
        
        wsRef.current.onopen = () => {
          reconnectAttempts = 0; // Reset on successful connection
          setConnectionStatus(prev => ({ ...prev, ws: 'Connected', sse: 'Connected' }));
          console.log('✅ WebSocket connected');
          refreshAllDashboardData();
          
          const pingInterval = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              const startTime = Date.now();
              wsRef.current.send(JSON.stringify({ 
                type: 'ping', 
                timestamp: startTime 
              }));
            }
          }, 20000); // Ping every 20 seconds
          
          wsRef.current.pingInterval = pingInterval;
        };
        
        wsRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'pong') {
              const rtt = Date.now() - data.timestamp;
              setWsRtt(`${rtt}ms`);
            } else {
              handleRealTimeUpdate(data);
            }
          } catch (err) {
            console.error('WebSocket message parse error:', err);
          }
        };
        
        wsRef.current.onclose = () => {
          setConnectionStatus(prev => ({ ...prev, ws: 'Disconnected', sse: 'Disconnected' }));
          setWsRtt(NOT_AVAILABLE);
          
          // Only reconnect if under max attempts
          if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            setTimeout(() => {
              console.log(`Reconnecting... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
              connectWebSocket();
            }, 5000);
          } else {
            console.log('❌ Max reconnect attempts reached');
          }
        };
        
        wsRef.current.onerror = (error) => {
          console.error('WebSocket error:', error);
          setConnectionStatus(prev => ({ ...prev, ws: 'Error', sse: 'Error' }));
        };
      } catch (err) {
        console.error('WebSocket connection error:', err);
        setConnectionStatus(prev => ({ ...prev, ws: 'Error', sse: 'Error' }));
      }
    };
    
    // Only use WebSocket (SSE disabled due to auth issues)
    try {
      connectWebSocket();
    } catch (err) {
      console.error('Failed to initialize WebSocket:', err);
      setConnectionStatus({ ws: 'Error', sse: 'Error', api: 'Connected' });
    }
  };

  // Rate limiter for unknown message types
  const unknownMessageRateLimit = useRef({ count: 0, lastReset: Date.now() });

  const handleRealTimeUpdate = (data) => {
    const eventType = typeof data.type === 'string' ? data.type.toLowerCase() : '';
    if (!eventType) {
      return;
    }
    switch (eventType) {
      case 'connection':
        // Handle WebSocket connection status updates
        setConnectionStatus(prev => ({
          ...prev,
          ws: data.status === 'Connected' ? 'Connected' : 'Disconnected',
          sse: data.status === 'Connected' ? 'Connected' : 'Disconnected'
        }));
        console.log('🔌 Connection status:', data.status);
        break;
      
      case 'ping':
        // Handle ping messages - update last seen timestamp silently
        setSseLastUpdate(new Date().toISOString());
        break;
      
      case 'metrics':
        setMetrics(prev => ({ ...prev, ...data.payload }));
        break;
      case 'bot_status':
        setBots(prev => prev.map(bot => 
          bot.id === data.payload.bot_id 
            ? { ...bot, ...data.payload.updates }
            : bot
        ));
        break;
      case 'balance':
        setBalances(prev => ({ ...prev, ...data.payload }));
        break;
      case 'live_prices': {
        // Real-time price update from SSE or WebSocket
        const normalizedPrices = normalizeLivePrices(data.prices || data.payload, null);
        if (normalizedPrices) {
          setLivePrices(prev => ({ ...prev, ...normalizedPrices }));
        }
        break;
      }
      case 'prices_update': {
        const normalizedPrices = normalizeLivePrices(data.data?.prices || data.prices, null);
        if (normalizedPrices) {
          setLivePrices(prev => ({ ...prev, ...normalizedPrices }));
        }
        break;
      }
      case 'overview_update': {
        const overview = data.data?.overview || data.overview;
        if (overview) {
          const totalBots = safeNumber(overview.bots_active, 0) + safeNumber(overview.bots_paused, 0) + safeNumber(overview.bots_training, 0) + safeNumber(overview.bots_quarantine, 0);
          setOverviewData(prev => ({ ...prev, ...overview }));
          setMetrics(prev => ({
            ...prev,
            totalProfit: `R${safeNumber(overview.total_profit, 0).toFixed(2)}`,
            activeBots: `${safeNumber(overview.bots_active, 0)} / ${totalBots}`,
            lastUpdate: formatTimestamp(new Date(), { includeDate: false })
          }));
        }
        break;
      }
      case 'bots_update': {
        const botsPayload = data.data?.bots || data.bots;
        if (Array.isArray(botsPayload)) {
          setBots(botsPayload);
        }
        break;
      }
      case 'trades_update': {
        const tradesPayload = data.data?.trades || data.trades;
        if (Array.isArray(tradesPayload)) {
          setRecentTrades(tradesPayload);
        }
        break;
      }
      case 'notification':
        showNotification(data.payload.message, data.payload.type || 'info');
        break;
      case 'chat_response':
        setChatMessages(prev => [...prev, { 
          role: 'assist', 
          content: data.payload.message 
        }]);
        break;
      case 'trade_executed':
        // Real-time trade feed update - only update state, don't reload
        setRecentTrades(prev => {
          // Prevent duplicates by checking if trade already exists
          const tradeExists = prev.some(t => t.id === data.trade?.id);
          if (tradeExists) return prev;
          
          return [{
            ...data.trade,
            bot_name: data.bot_name,
            timestamp: new Date().toISOString()
          }, ...prev.slice(0, 49)]; // Keep last 50 trades
        });
        
        // Update bot data
        setBots(prev => prev.map(bot => 
          bot.id === data.bot_id 
            ? { 
                ...bot, 
                current_capital: data.new_capital,
                total_profit: data.total_profit,
                name: bot.name || data.bot_name // Preserve bot name
              }
            : bot
        ));
        
        // Refresh metrics to show new profit
        loadMetrics();
        
        // Refresh analytics tabs if they are active
        if (profitsTab === 'equity') {
          loadEquityData();
        } else if (profitsTab === 'drawdown') {
          loadDrawdownData();
        } else if (profitsTab === 'win-rate') {
          loadWinRateData();
        } else if (profitsTab === 'profit-history') {
          loadProfitData();
        }
        break;
      
      case 'profit_update':
        // Real-time profit update in overview
        setMetrics(prev => ({
          ...prev,
          totalProfit: `R${safeToFixed(data.total_profit, 2)}`
        }));
        // Update countdown when profit changes
        loadCountdown();
        break;
      
      case 'overview_updated':
        // Update overview data from WebSocket
        if (data.overview) {
          setMetrics(prev => ({
            ...prev,
            totalProfit: Number.isFinite(Number(data.overview.portfolio_value))
              ? `R${safeToFixed(data.overview.portfolio_value, 2)}`
              : prev.totalProfit,
            activeBots: data.overview.active_bots !== undefined ? `${safeNumber(data.overview.active_bots, 0)}` : prev.activeBots,
            exposure: Number.isFinite(Number(data.overview.exposure)) ? `${safeToFixed(data.overview.exposure, 1, '0.0')}%` : prev.exposure,
            riskLevel: data.overview.risk_level || prev.riskLevel
          }));
          
          if (data.overview.todays_pnl !== undefined) {
            // Update today's P&L if provided
            setBalances(prev => ({
              ...prev,
              todays_pnl: data.overview.todays_pnl
            }));
          }
        }
        loadOverviewData();
        loadRiskStatus();
        break;
      case 'bot_status_changed':
        refreshBotState();
        loadMetrics();
        if (data.message) toast.info(data.message);
        break;
      
      case 'system_mode_update':
        // System mode changed
        setSystemModes(data.modes);
        toast.success('System modes updated');
        break;
      
      case 'bot_created':
        // Reload bots and metrics immediately
        refreshBotState();
        loadMetrics();
        if (data.message) toast.success(data.message);
        break;
      
      case 'bot_updated':
        // Update specific bot
        setBots(prev => prev.map(bot => 
          bot.id === data.bot_id ? { ...bot, ...data.changes } : bot
        ));
        break;
      case 'bot_paused':
      case 'bot_resumed':
        refreshBotState();
        loadMetrics();
        if (data.message) toast.info(data.message);
        break;
      
      case 'bot_deleted':
        // Reload bots list
        refreshBotState();
        loadMetrics();
        if (data.message) toast.success(data.message);
        break;
      
      case 'bot_promoted':
        // Bot promoted to live
        refreshBotState();
        if (data.message) toast.success(data.message);
        break;
      
      case 'api_key_update':
        // API key connected/updated
        loadApiStatuses();
        if (data.message) toast.success(data.message);
        break;
      
      case 'key_saved':
        // API key saved (realtime event)
        console.log('🔑 Key saved event:', data);
        loadApiStatuses();
        if (data.message) toast.success(data.message);
        break;
      
      case 'key_tested':
        // API key tested (realtime event)
        console.log('🔑 Key tested event:', data);
        loadApiStatuses();
        if (data.message) {
          if (data.success) {
            toast.success(data.message);
          } else {
            toast.error(data.message);
          }
        }
        break;
      
      case 'key_deleted':
        // API key deleted (realtime event)
        console.log('🔑 Key deleted event:', data);
        loadApiStatuses();
        if (data.message) toast.success(data.message);
        break;
      
      case 'autopilot_action':
        // Autopilot did something
        refreshBotState();
        loadMetrics();
        if (data.message) toast.info(data.message);
        break;
      
      case 'self_healing':
        // Self-healing paused a bot
        refreshBotState();
        if (data.message) toast.warning(data.message);
        break;
      
      case 'countdown_update':
        // Countdown changed
        loadCountdown();
        loadCustomCountdowns();
        break;
      
      // REMOVED: Duplicate trade_executed handler
      // Now handled above with state updates only (no full reload)
      
      case 'profit_updated':
        // Profit changed - update all profit displays
        loadMetrics();
        loadCountdown();
        loadCustomCountdowns();
        loadProfitData(graphPeriod);
        loadAutoSpawnStatus();
        loadAutopilotGrowthStatus();
        loadAutopilotReinvestStatus();
        break;
      
      case 'ai_evolution':
        // AI learning/evolution happened
        if (data.message) toast.info(data.message);
        loadBots(); // May have new bots
        break;
      
      case 'system_update':
        // General system update from AI
        refreshBotState();
        loadSystemModes();
        loadMetrics();
        if (data.success) {
          toast.success('System updated successfully');
        }
        break;
      
      case 'force_refresh':
        // FORCE IMMEDIATE REFRESH from AI action - COMPLETE STATE RESET
        console.log('🔄 FORCE REFRESH - Clearing ALL state');
        
        // Clear ALL state to zeros/empty first
        setProfitData({
          labels: [],
          values: [],
          total: 0,
          avg_daily: 0,
          best_day: 0,
          growth_rate: 0
        });
        setCountdown(null);
        setRecentTrades([]);
        setBots([]);
        setMetrics({
          total_profit: 0,
          total_trades: 0,
          win_rate: 0,
          active_bots: 0
        });
        
        // Clear browser cache for profit data
        sessionStorage.removeItem('profitData');
        sessionStorage.removeItem('recentTrades');
        
        // Wait a moment then reload everything
        setTimeout(() => {
          refreshAllDashboardData();
          loadProfitData();
          loadBalances();
        }, 100);
        
        if (data.message) {
          toast.success(data.message + ' - All data cleared!');
        }
        break;
      
      default:
        // Rate-limited debug logging for unknown message types
        const now = Date.now();
        if (now - unknownMessageRateLimit.current.lastReset > 60000) {
          // Reset counter every minute
          unknownMessageRateLimit.current = { count: 0, lastReset: now };
        }
        
        if (unknownMessageRateLimit.current.count < 5) {
          console.debug('Unknown real-time update:', data);
          unknownMessageRateLimit.current.count++;
        } else if (unknownMessageRateLimit.current.count === 5) {
          console.debug('Unknown message types rate limit reached. Suppressing further logs for 1 minute.');
          unknownMessageRateLimit.current.count++;
        }
    }
  };

  const showNotification = (message, type = 'success') => {
    toast[type](message);
  };

  // Helper to extract error message from backend response
  const extractErrorMessage = (err, defaultMsg = 'An error occurred') => {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'object' && detail !== null) {
      return detail.message || detail.error || JSON.stringify(detail);
    }
    return detail || err.message || defaultMsg;
  };

  const loadUser = async () => {
    try {
      const res = await axios.get(`${API}/auth/me`, axiosConfig);
      setUser(res.data);
      setConnectionStatus(prev => ({ ...prev, api: 'Connected' }));
    } catch (err) {
      console.error('User fetch error:', err);
      setConnectionStatus(prev => ({ ...prev, api: 'Disconnected' }));
      if (err.response?.status === 401) navigate('/login');
    }
  };

  const loadBots = async () => {
    try {
      const res = await axios.get(`${API}/bots/status`, axiosConfig);
      const botsData = res.data?.bots || res.data || [];
      setBots(botsData);
      if (res.data?.success === false) {
        const now = Date.now();
        if (now - botStatusErrorRef.current.lastShown > 60000) {
          const message = res.data?.error || res.data?.message || 'Bot status unavailable';
          toast.error(`Bot status unavailable: ${message}`);
          botStatusErrorRef.current.lastShown = now;
        }
      }
    } catch (err) {
      console.error('Bots fetch error:', err);
      const now = Date.now();
      if (now - botStatusErrorRef.current.lastShown > 60000) {
        const statusLabel = err.response?.status ? ` (${err.response.status})` : '';
        const message = extractErrorMessage(err, 'Request failed');
        toast.error(`Bot status unavailable${statusLabel}: ${message}`);
        botStatusErrorRef.current.lastShown = now;
      }
    }
  };

  const loadOverviewData = async () => {
    try {
      const [snapshotResult, paperWalletResult, modeResult, tradesResult, autonomyResult, aiResult, learningResult] = await Promise.allSettled([
        get('/overview/snapshot'),
        get('/wallet/paper'),
        get('/system/mode'),
        get('/trades/recent?limit=1'),
        get('/autonomy/status'),
        get('/ai/status'),
        get('/learning/status')
      ]);

      const snapshotRes = snapshotResult.status === 'fulfilled' ? snapshotResult.value : {};
      const paperWalletRes = paperWalletResult.status === 'fulfilled' ? paperWalletResult.value : {};
      const modeRes = modeResult.status === 'fulfilled' ? modeResult.value : {};
      const tradesRes = tradesResult.status === 'fulfilled' ? tradesResult.value : {};
      const autonomyRes = autonomyResult.status === 'fulfilled' ? autonomyResult.value : null;
      const aiRes = aiResult.status === 'fulfilled' ? aiResult.value : null;
      const learningRes = learningResult.status === 'fulfilled' ? learningResult.value : null;

      const totalProfit = safeNumber(snapshotRes?.totalProfit, 0);
      const todaysTrades = safeNumber(snapshotRes?.todaysTrades, 0);
      const openPositions = safeNumber(snapshotRes?.openPositions, 0);
      const winRate = safeNumber(snapshotRes?.winRate, 0);
      const activeBots = safeNumber(snapshotRes?.activeBots, 0);
      const paperWalletTotal = safeNumber(paperWalletRes?.total, 0);
      const paperWalletAllocated = Object.values(paperWalletRes?.allocated || {}).reduce(
        (sum, value) => sum + safeNumber(value, 0),
        0
      );
      const systemMode = snapshotRes?.systemMode || resolveSystemMode(modeRes);
      const lastTradeTime = tradesRes?.trades?.[0]?.timestamp || null;

      setOverviewData({
        totalProfit,
        todaysTrades,
        openPositions,
        winRate,
        activeBots,
        paperWalletTotal,
        paperWalletAllocated,
        lastTradeTime,
        systemMode,
        lastRebalance: snapshotRes?.lastRebalance || 'Not available',
        nextReinvest: snapshotRes?.nextReinvest || 'Not available'
      });
      setAutonomyStatus(autonomyRes);
      setAiStatus(aiRes);
      setLearningStatus(learningRes);
    } catch (err) {
      console.error('Overview data fetch error:', err);
    }
  };

  const loadRiskStatus = async () => {
    try {
      const res = await get('/risk/status');
      setRiskStatus(res);
    } catch (err) {
      console.error('Risk status fetch error:', err);
      notifyError(err);
    }
  };

  const loadAutoSpawnStatus = async () => {
    try {
      const res = await get('/diagnostics/auto-spawn');
      setAutoSpawnStatus(res);
    } catch (err) {
      console.error('Auto-spawn status fetch error:', err);
      notifyError(err);
      setAutoSpawnStatus(null);
    }
  };

  const loadAutopilotGrowthStatus = async () => {
    try {
      const res = await axios.get(`${API}/autopilot/growth/status`, axiosConfig);
      setAutopilotGrowthStatus(res.data);
    } catch (err) {
      console.error('Autopilot growth status fetch error:', err);
      notifyError(err);
      setAutopilotGrowthStatus(null);
    }
  };

  const loadAutopilotReinvestStatus = async () => {
    try {
      const res = await axios.get(`${API}/autopilot/reinvest/status`, axiosConfig);
      setAutopilotReinvestStatus(res.data);
    } catch (err) {
      console.error('Autopilot reinvest status fetch error:', err);
      notifyError(err);
      setAutopilotReinvestStatus(null);
    }
  };

  const handleResumeBot = async (botId) => {
    setBotControlLoading(prev => ({ ...prev, [botId]: true }));
    try {
      await post(`/bots/${botId}/resume`, {});
      toast.success('Bot resumed successfully');
      await refreshBotState();
    } catch (err) {
      const errorMsg = formatActionError(err, 'Failed to resume bot');
      toast.error(`Error: ${errorMsg} (${err.response?.status || 'Network Error'})`);
    } finally {
      setBotControlLoading(prev => ({ ...prev, [botId]: false }));
    }
  };

  const handleStartBot = async (botId) => {
    setBotControlLoading(prev => ({ ...prev, [botId]: true }));
    try {
      await post(`/bots/${botId}/start`, {});
      toast.success('Bot started successfully');
      await refreshBotState();
    } catch (err) {
      const errorMsg = formatActionError(err, 'Failed to start bot');
      toast.error(`Error: ${errorMsg} (${err.response?.status || 'Network Error'})`);
    } finally {
      setBotControlLoading(prev => ({ ...prev, [botId]: false }));
    }
  };

  const handleResumeAllBots = async () => {
    setBotControlLoading(prev => ({ ...prev, 'all': true }));
    try {
      await post('/risk/resume-all', {});
      toast.success('All bots resumed successfully');
      await refreshBotState();
    } catch (err) {
      const errorMsg = formatActionError(err, 'Failed to resume all bots');
      toast.error(`Error: ${errorMsg} (${err.response?.status || 'Network Error'})`);
    } finally {
      setBotControlLoading(prev => ({ ...prev, 'all': false }));
    }
  };

  const handleResetDailyLossLock = async () => {
    const confirmText = window.prompt('Type "RESET_RISK_LOCK" to confirm resetting the daily loss lock:');
    if (confirmText !== 'RESET_RISK_LOCK') {
      toast.error('Reset cancelled - confirmation text did not match');
      return;
    }
    
    try {
      await post('/risk/daily-loss-lock/reset?confirmation=RESET_RISK_LOCK', {});
      toast.success('Daily loss lock has been reset');
      await loadRiskStatus();
      await refreshBotState();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to reset lock';
      toast.error(`Error: ${errorMsg} (${err.response?.status || 'Network Error'})`);
    }
  };

  const handleResetBodyguardLock = async () => {
    const confirmText = window.prompt('Type "RESET_BODYGUARD_LOCK" to confirm resetting bodyguard locks:');
    if (confirmText !== 'RESET_BODYGUARD_LOCK') {
      toast.error('Reset cancelled - confirmation text did not match');
      return;
    }

    try {
      await post('/risk/bodyguard/reset?confirmation=RESET_BODYGUARD_LOCK', {});
      toast.success('Bodyguard locks have been reset');
      await loadRiskStatus();
      await refreshBotState();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to reset bodyguard lock';
      toast.error(`Error: ${errorMsg} (${err.response?.status || 'Network Error'})`);
    }
  };

  const loadRecentTrades = async () => {
    try {
      const res = await axios.get(`${API}/trades/recent?limit=50`, axiosConfig);
      // Handle both array responses and wrapped responses
      const trades = Array.isArray(res.data) ? res.data : (res.data.trades || res.data.data || []);
      setRecentTrades(trades);
      // Clear any previous error
      if (window.tradesErrorToast) {
        window.tradesErrorToast = null;
      }
    } catch (err) {
      console.error('Recent trades fetch error:', err);
      const statusCode = err.response?.status || 'Network Error';
      const endpoint = '/api/trades/recent';
      const errorMsg = err.response?.data?.detail || err.message || 'Unknown error';
      
      // Show persistent error banner/toast
      if (!window.tradesErrorToast) {
        window.tradesErrorToast = toast.error(
          `Failed to load trades (${statusCode}): ${errorMsg} • Endpoint: ${endpoint}`,
          { duration: 10000 }
        );
      }
    }
  };

  const loadMetrics = async () => {
    try {
      const res = await axios.get(`${API}/portfolio/summary`, axiosConfig);
      setMetrics({
        totalProfit: `R${safeToFixed(res.data.net_pnl, 2)}`,
        activeBots: `${safeNumber(res.data.active_bots, 0)} / ${safeNumber(res.data.total_bots, 0)}`,
        exposure: `${safeToFixed(res.data.exposure, 1, '0.0')}%`,
        riskLevel: res.data.risk_level || 'Unknown',
        aiSentiment: res.data.ai_sentiment || 'Neutral',
        lastUpdate: new Date().toLocaleTimeString() || NOT_AVAILABLE
      });
    } catch (err) {
      console.error('Metrics fetch error:', err);
    }
  };

  const loadSystemModes = async () => {
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
  };

  const loadApiStatuses = async () => {
    try {
      const res = await axios.get(`${API}/keys/status`, axiosConfig);
      const statusMap = res.data?.status_map || {};
      setApiKeys(statusMap);
    } catch (err) {
      console.error('API keys fetch error:', err);
    }
  };

  const loadCountdown = async () => {
    try {
      const res = await axios.get(`${API}/analytics/countdown-to-million`, axiosConfig);
      setCountdown(res.data);
    } catch (err) {
      console.error('Countdown fetch error:', err);
    }
  };

  const loadCustomCountdowns = async () => {
    try {
      const res = await axios.get(`${API}/countdowns`, axiosConfig);
      setCustomCountdowns(res.data || []);
    } catch (err) {
      console.error('Custom countdowns fetch error:', err);
    }
  };

  const addCustomCountdown = async () => {
    try {
      if (!newCountdownLabel.trim() || !newCountdownAmount || parseFloat(newCountdownAmount) <= 0) {
        toast.error('Please enter valid countdown details');
        return;
      }

      await axios.post(`${API}/countdowns`, {
        label: newCountdownLabel.trim(),
        target_amount: parseFloat(newCountdownAmount)
      }, axiosConfig);

      toast.success('Countdown added successfully!');
      setNewCountdownLabel('');
      setNewCountdownAmount('');
      setShowAddCountdown(false);
      await loadCustomCountdowns();
    } catch (err) {
      console.error('Add countdown error:', err);
      toast.error(err.response?.data?.detail || 'Failed to add countdown');
    }
  };

  const deleteCustomCountdown = async (countdownId) => {
    try {
      await axios.delete(`${API}/countdowns/${countdownId}`, axiosConfig);
      toast.success('Countdown deleted');
      await loadCustomCountdowns();
    } catch (err) {
      console.error('Delete countdown error:', err);
      toast.error('Failed to delete countdown');
    }
  };

  const loadStorageData = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/storage`, axiosConfig);
      setStorageData(res.data);
      setStorageError(null);
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to load storage data';
      console.error('Storage data fetch error:', err);
      setStorageError(message);
      toast.error(message);
    }
  }, [axiosConfig]);

  const checkEligibleBots = async () => {
    try {
      const res = await axios.get(`${API}/bots/eligible-for-promotion`, axiosConfig);
      if (res.data.count > 0) {
        setEligibleBots(res.data.eligible_bots);
        setShowPromotionModal(true);
      }
    } catch (err) {
      console.error('Eligible bots check error:', err);
    }
  };

  const confirmLiveSwitch = async (lunoFunded, usePaperBots) => {
    try {
      const res = await axios.post(`${API}/bots/confirm-live-switch`, {
        luno_funded: lunoFunded,
        use_paper_bots: usePaperBots
      }, axiosConfig);
      toast.success(res.data.message || 'Bots switched to live trading!');
      setShowPromotionModal(false);
      loadBots();
      loadSystemModes();
    } catch (err) {
      console.error('Live switch error:', err);
      toast.error(extractErrorMessage(err, 'Failed to switch to live trading'));
    }
  };


  const loadBalances = async () => {
    try {
      const res = await axios.get(`${API}/wallet/balances`, axiosConfig);
      setBalances({
        zar: res.data.zar || 0,
        btc: res.data.btc || 0
      });
    } catch (err) {
      console.error('Balances fetch error:', err);
    }
  };

  const loadProfitData = async () => {
    try {
      const res = await axios.get(`${API}/analytics/profit-history?period=${graphPeriod}`, axiosConfig);
      setProfitData(res.data);
    } catch (err) {
      console.error('Profit data error:', err);
      setProfitData({
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        values: [0, 0, 0, 0, 0, 0, 0],
        total: 0,
        avg_daily: 0,
        best_day: 0,
        growth_rate: 0
      });
    }
  };

  const loadEquityData = async () => {
    try {
      const res = await axios.get(`${API}/analytics/equity?range=${equityRange}`, axiosConfig);
      setEquityData(res.data);
    } catch (err) {
      console.error('Equity data error:', err);
      setEquityData(null);
    }
  };

  const loadDrawdownData = async () => {
    try {
      const res = await axios.get(`${API}/analytics/drawdown?range=${drawdownRange}`, axiosConfig);
      setDrawdownData(res.data);
    } catch (err) {
      console.error('Drawdown data error:', err);
      setDrawdownData(null);
    }
  };

  const loadWinRateData = async () => {
    try {
      const res = await axios.get(`${API}/analytics/win_rate?period=${winRatePeriod}`, axiosConfig);
      setWinRateData(res.data);
    } catch (err) {
      console.error('Win rate data error:', err);
      setWinRateData(null);
    }
  };

  const calculateProjection = async () => {
    // This function now fetches from countdown endpoint
    // Note: loadCountdown() is already called, so we just ensure projection state matches countdown
    if (countdown) {
      setProjection({
        days_to_million: countdown.days_remaining < 9999 ? countdown.days_remaining : '∞',
        current_balance: countdown.current_capital,
        daily_growth_rate: safeToFixed(countdown.metrics?.daily_roi_pct, 3, '0.000'),
        progress_percentage: safeToFixed(countdown.progress_pct, 1, '0.0'),
        projected_annual: safeToFixed(safeNumber(countdown.metrics?.avg_daily_profit, 0) * 365, 2, '0.00'),
        compound_effect: countdown.projections?.using === 'compound' ? 100 : 0
      });
    }
  };

  const loadDepositAddress = async () => {
    try {
      const res = await axios.get(`${API}/wallet/deposit-address`, axiosConfig);
      setDepositAddress(res.data);
    } catch (err) {
      console.error('Deposit address error:', err);
    }
  };

  const loadAllUsers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/users`, axiosConfig);
      setAllUsers(res.data.users || []);
    } catch (err) {
      console.error('Admin users error:', err);
      setAllUsers([]);
    }
  }, [axiosConfig]);

  const loadSystemStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/system-stats`, axiosConfig);
      setSystemStats(res.data);
    } catch (err) {
      console.error('System stats error:', err);
    }
  }, [axiosConfig]);

  const loadSystemHealth = async () => {
    try {
      const res = await axios.get(`${API}/system/status`, axiosConfig);
      const data = res.data;
      
      // Update systemHealth state with real data
      setSystemHealth({
        status: data.database?.connected ? 'Healthy' : 'Degraded',
        errors: (data.scheduler_status?.errors || []).length,
        uptime: data.uptime || NOT_AVAILABLE,
        lastCheck: new Date().toLocaleTimeString()
      });
      
      // Also update metrics with trading activity data if available
      if (data.trading_activity) {
        setMetrics(prev => ({
          ...prev,
          activeBots: `${data.trading_activity.active_bots || 0} / ${data.trading_activity.total_bots || 0}`,
          lastUpdate: data.trading_activity.last_trade_time 
            ? new Date(data.trading_activity.last_trade_time).toLocaleString()
            : prev.lastUpdate
        }));
      }
    } catch (err) {
      console.error('System health error:', err);
      setSystemHealth({
        status: 'Unknown',
        errors: 0,
        uptime: NOT_AVAILABLE,
        lastCheck: new Date().toLocaleTimeString()
      });
    }
  };

  const loadFlokxStatus = async () => {
    try {
      const res = await axios.get(`${API}/flokx/status`, axiosConfig);
      const status = res.data || {};
      setFlokxStatus(status);
      setIsFlokxActive(Boolean(status.configured));
    } catch (err) {
      console.error('Flokx status error:', err);
      setFlokxStatus({ configured: false, last_error: extractErrorMessage(err, 'Unavailable'), last_tested_at: null });
      setIsFlokxActive(false);
    }
  };

  const loadAdminHealth = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/health-check`, axiosConfig);
      setAdminApiHealth({
        status: res.data?.health_status || 'Healthy',
        lastCheck: new Date().toISOString(),
        error: null
      });
    } catch (err) {
      const errorMsg = extractErrorMessage(err, 'Admin health check failed');
      setAdminApiHealth({
        status: 'Error',
        lastCheck: new Date().toISOString(),
        error: errorMsg
      });
      toast.error(errorMsg);
    }
  }, [axiosConfig]);

  const loadFlokxAlerts = async () => {
    try {
      const res = await axios.get(`${API}/flokx/alerts`, axiosConfig);
      setFlokxAlerts(res.data?.alerts || []);
    } catch (err) {
      console.error('Flokx alerts error:', err);
      setFlokxAlerts([]);
    }
  };

  const handleSendMessage = async () => {
    if (chatSending) {
      showNotification('A message is already being sent. Please wait.', 'info');
      return;
    }
    const originalInput = chatInput.trim();
    if (!originalInput) return;

    setChatSending(true);
    try {
      const userMsg = { role: 'user', content: originalInput };
      setChatMessages(prev => [...prev, userMsg]);
      const msgLower = originalInput.toLowerCase(); // Case-insensitive for command matching
      setChatInput('');

      // PHASE 12: Save user message to backend
      try {
        await post('/ai/chat', {
          role: 'user',
          content: originalInput,
          log_only: true,
          metadata: { timestamp: new Date().toISOString() }
        });
      } catch (error) {
        console.error('Failed to save chat message:', error);
      }

      // PHASE 11: Handle admin commands with backend verification
      if (awaitingPassword) {
        try {
          // Verify password with backend
          const result = await post('/admin/unlock', { password: originalInput });
          
            if (adminAction === 'show') {
              console.log('🔓 SHOWING ADMIN - Setting state to TRUE');
              setShowAdmin(true);
              
              // Success feedback message
              const successMsg = { role: 'assistant', type: 'system', content: '✅ Admin panel unlocked successfully! Switching to admin section...' };
              setChatMessages(prev => [...prev, successMsg]);
            
            // Auto-hide after 1 hour
              setTimeout(() => {
                setShowAdmin(false);
                toast.info('Admin session expired');
              }, 3600000);
            
            // Auto-switch to admin section
            setTimeout(() => {
              setActiveSection('admin');
              console.log('Admin section activated, showAdmin:', true);
            }, 100);
            
            // Save success message
            try {
              await post('/ai/chat', {
                role: 'assistant',
                content: successMsg.content,
                log_only: true,
                metadata: { timestamp: new Date().toISOString() }
              });
            } catch (error) {
              console.error('Failed to save assistant message:', error);
            }
          } else if (adminAction === 'hide') {
            console.log('🔒 HIDING ADMIN - Setting state to FALSE');
            const currentlyInAdmin = activeSection === 'admin';
            
              setShowAdmin(false);
              
              // If currently viewing admin, switch to welcome
            if (currentlyInAdmin) {
              setActiveSection('welcome');
            }
            
            // Success feedback message
            const successMsg = { role: 'assistant', type: 'system', content: '✅ Admin panel hidden successfully.' };
            setChatMessages(prev => [...prev, successMsg]);
            console.log('Admin section deactivated, showAdmin:', false);
            
            // Save success message
            try {
            await post('/ai/chat', {
              role: 'assistant',
              content: successMsg.content,
              log_only: true,
              metadata: { timestamp: new Date().toISOString() }
            });
          } catch (error) {
            console.error('Failed to save assistant message:', error);
            }
          }
          
          setAwaitingPassword(false);
          setAdminAction(null);
        } catch (error) {
          console.log('❌ WRONG PASSWORD:', originalInput);
          const errorMsg = { 
            role: 'assistant', 
            type: 'system',
            content: '❌ Invalid admin password. Access denied. Please try again with the correct password.' 
          };
          setChatMessages(prev => [...prev, errorMsg]);
          
          setAwaitingPassword(false);
          setAdminAction(null);
          
          // Save error message
          try {
            await post('/ai/chat', {
              role: 'assistant',
              content: errorMsg.content,
              log_only: true,
              metadata: { timestamp: new Date().toISOString(), error: true }
            });
          } catch (error) {
            console.error('Failed to save assistant message:', error);
          }
        }
        
        return;
      }

      // Handle show/hide admin commands - CASE-INSENSITIVE and WHITESPACE-TOLERANT
      if (msgLower === 'show admin' || msgLower === 'showadmin' || msgLower === 'show admn') {
        setAwaitingPassword(true);
        setAdminAction('show');
        const assistantMsg = { role: 'assistant', content: '🔐 Please enter the admin password to show the admin section:' };
        setChatMessages(prev => [...prev, assistantMsg]);
        
        // Save assistant message
        try {
          await post('/ai/chat', {
            role: 'assistant',
            content: assistantMsg.content,
            log_only: true,
            metadata: { timestamp: new Date().toISOString() }
          });
        } catch (error) {
          console.error('Failed to save assistant message:', error);
        }
        
        return;
      }

      if (msgLower === 'hide admin' || msgLower === 'hideadmin') {
        setAwaitingPassword(true);
        setAdminAction('hide');
        const assistantMsg = { role: 'assistant', content: '🔐 Please enter the admin password to hide admin panel:' };
        setChatMessages(prev => [...prev, assistantMsg]);
        
        // Save assistant message
        try {
          await post('/ai/chat', {
            role: 'assistant',
            content: assistantMsg.content,
            log_only: true,
            metadata: { timestamp: new Date().toISOString() }
          });
        } catch (error) {
          console.error('Failed to save assistant message:', error);
        }
        
        return;
      }

      // Send all other messages to AI backend
      try {
        const res = await axios.post(`${API}/chat/message`, {
          message: originalInput,
          context: 'dashboard',
          request_action: true
        }, axiosConfig);
        const payload = res.data || {};
        if (payload?.error_code === 'OPENAI_KEY_MISSING') {
          setChatMessages(prev => [...prev, {
            role: 'assistant',
            content: 'Set your OpenAI API key in API Setup to enable Super Brain Chat.',
            error: true
          }]);
          return;
        }
        if (payload?.success === false || payload?.error) {
          const errorContent = payload?.reply || payload?.message || payload?.content || payload?.error || payload?.detail || 'AI chat error.';
          setChatMessages(prev => [...prev, { role: 'assistant', content: errorContent, error: true }]);
          return;
        }
        const reply = typeof payload === 'string'
          ? payload
          : (payload.reply || payload.content || payload.response || payload.message || 'No response');
        let finalReply = reply;
        if (payload?.action_attempted && payload?.action_result && payload?.action_result !== 'success') {
          const statusLabel = payload.action_result === 'blocked' ? '⛔ Action blocked' : '❌ Action failed';
          const reason = payload.reason ? `: ${payload.reason}` : '';
          finalReply = `${reply}\n\n${statusLabel}${reason}`;
        }
        const assistantMsg = { role: 'assistant', content: finalReply };
        setChatMessages(prev => [...prev, assistantMsg]);
        if (payload?.action_attempted && payload?.action_result === 'success') {
          refreshAllDashboardData();
        }
        
        // PHASE 12: Save assistant message to backend
        try {
          await post('/ai/chat', {
            role: 'assistant',
            content: finalReply,
            log_only: true,
            metadata: { timestamp: new Date().toISOString() }
          });
        } catch (error) {
          console.error('Failed to save assistant message:', error);
        }
      } catch (err) {
        console.error('Chat error:', err);
        const errorMsg = { role: 'assistant', content: `AI error: ${err.message}` };
        setChatMessages(prev => [...prev, errorMsg]);
        
        // Save error message
        try {
          await post('/ai/chat', {
            role: 'assistant',
            content: errorMsg.content,
            log_only: true,
            metadata: { timestamp: new Date().toISOString(), error: true }
          });
        } catch (error) {
          console.error('Failed to save error message:', error);
        }
      }
    } finally {
      setChatSending(false);
    }
  };

  const handleChatKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const handleLogout = () => {
    // Clear all storage including admin state and chat history
    localStorage.clear();
    sessionStorage.clear();
    
    // Reset showAdmin state
    setShowAdmin(false);
    
    // Clear chat messages
    setChatMessages([]);
    
    navigate('/login');
  };

  const showSection = (section) => {
    if (section === 'spawn') {
      setBotManagementTab('spawn');
      setActiveSection('bots');
      return;
    }
    setActiveSection(section);
  };

  const toggleSystemMode = async (mode) => {
    const newValue = !systemModes[mode];
    
    // Paper and Live trading are mutually exclusive
    if (mode === 'liveTrading' && newValue) {
      try {
        const walletRequirements = await get('/wallet/requirements');
        const summary = walletRequirements?.summary || {};
        const shortfall = Number(summary.shortfall_zar || 0);
        const requiredExchanges = Object.values(walletRequirements?.requirements || {}).map(req => req.exchange);
        const exchangesWithInvalidKeys = requiredExchanges.filter(
          exchange => apiKeys?.[exchange]?.status !== 'configured_valid'
        );

        if (shortfall > 0) {
          showNotification(`Live trading blocked: Wallet shortfall R${safeToFixed(shortfall, 2)}. Fund wallet first.`, 'error');
          return;
        }
        if (exchangesWithInvalidKeys.length > 0) {
          showNotification(`Live trading blocked: Configure and test API keys for ${exchangesWithInvalidKeys.join(', ')}.`, 'error');
          return;
        }
      } catch (err) {
        console.error('Live trading precheck error:', err);
        showNotification('Unable to verify live trading readiness. Try again.', 'error');
        return;
      }
      if (!window.confirm('⚠️ WARNING: This will enable REAL trading with REAL money. Are you sure?')) {
        return;
      }
    }
    
    try {
      // Send update to backend FIRST (single source of truth)
      const payload = { mode, enabled: newValue };
      if (mode === 'liveTrading' && newValue) {
        payload.confirmation_token = 'CONFIRM_LIVE_TRADING';
      }
      await axios.put(`${API}/system/mode`, payload, axiosConfig);
      
      // Fetch fresh state from backend to ensure sync
      await loadSystemModes();
      
      // Show appropriate notification
      if (mode === 'paperTrading' && newValue) {
        showNotification('Paper Trading activated. Live Trading disabled.');
      } else if (mode === 'liveTrading' && newValue) {
        showNotification('Live Trading activated. Paper Trading disabled.');
      } else {
        showNotification(`${mode} ${newValue ? 'activated' : 'deactivated'}`);
      }
    } catch (err) {
      console.error('Mode toggle error:', err);
      showNotification('Failed to update mode', 'error');
      // Reload state to revert UI to actual backend state
      loadSystemModes();
    }
  };

  const handleEmergencyStop = () => {
    setShowEmergencyConfirm(true);
  };

  const executeEmergencyStop = async () => {
    try {
      await axios.post(`${API}/system/emergency-stop`, {}, axiosConfig);
      showNotification('🚨 EMERGENCY STOP ACTIVATED - All systems halted', 'error');
      setSystemModes({ paperTrading: false, liveTrading: false, autopilot: false });
      loadBots();
    } catch (err) {
      console.error('Emergency stop error:', err);
      showNotification('Emergency stop failed', 'error');
      notifyError(err);
    } finally {
      setShowEmergencyConfirm(false);
    }
  };

  const handlePaperReset = async (confirmPhrase) => {
    if (!confirmPhrase || confirmPhrase !== 'START FRESH') {
      setPaperResetError('Please type "START FRESH" to confirm.');
      return;
    }
    try {
      setPaperResetLoading(true);
      setPaperResetError('');
      const response = await axios.post(`${API}/admin/start-fresh`, { 
        confirmation_phrase: confirmPhrase,
        scope: 'paper_only',
        also_reset_risk_locks: true
      }, axiosConfig);
      
      if (response.data.ok) {
        toast.success(response.data.message || 'Reset runtime completed successfully');
        setShowPaperResetModal(false);
        // Clear dashboard state
        setChatMessages([]);
        setBots([]);
        setRecentTrades([]);
        setAutoSpawnStatus(null);
        setAutopilotGrowthStatus(null);
        setAutopilotReinvestStatus(null);
        setCountdown(null);
        setCustomCountdowns([]);
        setOverviewData({
          totalProfit: 0,
          todaysTrades: 0,
          openPositions: 0,
          winRate: 0,
          activeBots: 0,
          paperWalletTotal: 0,
          paperWalletAllocated: 0,
          lastTradeTime: null,
          systemMode: 'paper',
          lastRebalance: NOT_AVAILABLE,
          nextReinvest: NOT_AVAILABLE
        });
        setMetrics({
          totalProfit: 'R0.00',
          activeBots: '0 / 0',
          exposure: '0%',
          riskLevel: NOT_AVAILABLE,
          aiSentiment: NOT_AVAILABLE,
          lastUpdate: NOT_AVAILABLE
        });
        refreshAllDashboardData();
      } else {
        setPaperResetError(response.data.message || 'Reset failed');
      }
    } catch (err) {
      const statusCode = err.response?.status;
      if (statusCode === 403) {
        setPaperResetError('Access denied. Admin privileges required.');
      } else if (statusCode === 400) {
        setPaperResetError(err.response?.data?.detail || 'Invalid confirmation phrase or request.');
      } else {
        setPaperResetError(extractErrorMessage(err, 'Reset runtime failed. Please try again.'));
      }
    } finally {
      setPaperResetLoading(false);
    }
  };

  const handleRiskProfileChange = async (newProfile) => {
    try {
      setRiskProfile(newProfile);
      await axios.put(`${API}/auth/profile`, { risk_profile: newProfile }, axiosConfig);
      setUser(prev => prev ? { ...prev, risk_profile: newProfile } : prev);
      showNotification(`Risk profile set to ${newProfile.toUpperCase()}`);
    } catch (err) {
      console.error('Risk profile update error:', err);
      showNotification('Failed to update risk profile', 'error');
      setRiskProfile(user?.risk_profile || 'balanced');
    }
  };

  const toggleApiExpand = (provider) => {
    setExpandedApis(prev => ({ ...prev, [provider]: !prev[provider] }));
  };

  const handleCreateBot = async (e) => {
    e.preventDefault();
    const name = e.target['bot-name'].value;
    const budget = parseInt(e.target['bot-budget'].value);
    const exchange = e.target['bot-exchange'].value;
    const riskMode = e.target['bot-risk'].value;
    const allowedPresets = ['adaptive', 'trend', 'mean_reversion', 'scalping'];
    const selectedPreset = e.target['bot-strategy']?.value || 'adaptive';
    const strategyPreset = allowedPresets.includes(selectedPreset) ? selectedPreset : 'adaptive';
    
    if (!name) {
      showNotification('Please enter a bot name', 'error');
      return;
    }

    if (budget < 1000) {
      showNotification('Minimum budget is R1000', 'error');
      return;
    }

    try {
      // Prepare bot data - USER CREATED = 7 day learning period
      const botData = {
        name,
        exchange,
        trading_mode: 'paper', // Always start in paper for user bots
        risk_mode: riskMode,
        initial_capital: budget,
        strategy_preset: strategyPreset,
        created_by: 'user', // Track origin
        paper_start_date: new Date().toISOString(), // Start 7-day countdown
        learning_complete: false
      };
      
      await axios.post(`${API}/bots`, botData, axiosConfig);
      showNotification(`Bot "${name}" created! Starting 7-day learning period.`, 'success');
      await refreshBotState();
      e.target.reset();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const errorMsg = typeof detail === 'object' ? detail.message || JSON.stringify(detail) : detail || 'Failed to create bot';
      showNotification(errorMsg, 'error');
      console.error('Bot creation error:', err);
    }
  };

  const handleCreateUAgent = async (e) => {
    e.preventDefault();
    const name = e.target['uagent-name'].value;
    const file = e.target['uagent-file'].files[0];
    const strategy = e.target['uagent-strategy'].value;
    
    if (!name || !file) {
      showNotification('Please provide name and file', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('name', name);
    formData.append('file', file);
    formData.append('strategy', strategy);
    formData.append('type', 'uagent');

    try {
      await axios.post(`${API}/bots/uagent`, formData, {
        ...axiosConfig,
        headers: {
          ...axiosConfig.headers,
          'Content-Type': 'multipart/form-data'
        }
      });
      showNotification(`uAgent "${name}" deployed successfully!`);
      await refreshBotState();
      e.target.reset();
    } catch (err) {
      showNotification('Failed to deploy uAgent', 'error');
    }
  };

  const handleCreateFlokxBot = async (e) => {
    e.preventDefault();
    const name = e.target['flokx-name'].value;
    const signalType = e.target['flokx-signal'].value;
    const riskLevel = e.target['flokx-risk'].value;
    
    if (!name) {
      showNotification('Please enter a bot name', 'error');
      return;
    }

    try {
      await axios.post(`${API}/bots/flokx`, { 
        name, 
        signal_type: signalType, 
        risk_level: riskLevel,
        type: 'flokx'
      }, axiosConfig);
      showNotification(`Flokx bot "${name}" created successfully!`);
      await refreshBotState();
      e.target.reset();
    } catch (err) {
      showNotification('Failed to create Flokx bot', 'error');
    }
  };

  const handleDeleteBot = async (botId) => {
    if (!window.confirm('Delete this bot? This cannot be undone.')) return;
    
    try {
      await axios.delete(`${API}/bots/${botId}`, axiosConfig);
      showNotification('Bot deleted');
      await refreshBotState();
    } catch (err) {
      showNotification('Failed to delete bot', 'error');
    }
  };

  const handleSaveBotName = async (botId) => {
    try {
      await axios.put(`${API}/bots/${botId}`, { name: editingBotName }, axiosConfig);
      showNotification('Bot name updated');
      setEditingBotId(null);
      setEditingBotName('');
      await refreshBotState();
    } catch (err) {
      showNotification('Failed to update bot name', 'error');
    }
  };

  const handleChangeRiskMode = async (botId, newRiskMode) => {
    try {
      await axios.put(`${API}/bots/${botId}`, { risk_mode: newRiskMode }, axiosConfig);
      showNotification(`Risk mode changed to ${newRiskMode.toUpperCase()}`);
      await refreshBotState();
    } catch (err) {
      showNotification('Failed to change risk mode', 'error');
    }
  };

  const handleToggleBotMode = async (botId, currentMode) => {
    const newMode = currentMode === 'paper' ? 'live' : 'paper';
    
    if (newMode === 'live') {
      if (!window.confirm('⚠️ WARNING: Switch to LIVE trading with REAL money?\n\nThis bot will trade with actual funds. Are you sure?')) {
        return;
      }
    }
    
    try {
      await axios.put(`${API}/bots/${botId}`, { trading_mode: newMode }, axiosConfig);
      showNotification(`✅ Bot switched to ${newMode.toUpperCase()} mode`);
      await refreshBotState();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Failed to change bot mode';
      showNotification(`❌ ${errorMsg}`, 'error');
    }
  };

  const handleBotSetup = async () => {
    const { count, capital_per_bot, safe_count, risky_count, aggressive_count } = botSetup;
    
    // Validation
    if (count < 3 || count > 30) {
      showNotification('❌ Bot count must be between 3 and 30', 'error');
      return;
    }
    
    if (safe_count + risky_count + aggressive_count !== count) {
      showNotification('❌ Risk distribution must equal total bot count', 'error');
      return;
    }
    
    if (capital_per_bot < 1000) {
      showNotification('❌ Minimum capital per bot is R1000', 'error');
      return;
    }
    
    const total_capital = safeNumber(count, 0) * safeNumber(capital_per_bot, 0);
    const confirm_msg = `🤖 Create ${count} bots with R${safeNumber(total_capital, 0).toLocaleString()} total capital?\n\n` +
      `💰 R${safeNumber(capital_per_bot, 0).toLocaleString()} per bot\n` +
      `🛡️ ${safe_count} Safe bots\n` +
      `⚡ ${risky_count} Risky bots\n` +
      `🚀 ${aggressive_count} Aggressive bots\n\n` +
      `All bots will start in PAPER mode with FAKE funds for 7 days.`;
    
    if (!window.confirm(confirm_msg)) return;
    
    try {
      const res = await axios.post(`${API}/bots/batch-create`, botSetup, axiosConfig);
      const createdCount = res.data.bots?.length || res.data.created || botSetup.count;
      showNotification(`✅ Created ${createdCount} bots successfully!`, 'success');
      await refreshBotState();
      showSection('bots');
    } catch (err) {
      const detail = err.response?.data?.detail;
      const errorMsg = typeof detail === 'object' ? detail.message || JSON.stringify(detail) : detail || 'Failed to create bots';
      showNotification(`❌ ${errorMsg}`, 'error');
    }
  };

  const handleSaveApiKey = async (provider) => {
    const formId = `form-${provider}`;
    const form = document.getElementById(formId);
    if (!form) return;

    const inputs = form.querySelectorAll('input');
    const data = { provider: provider.toLowerCase() }; // Backend expects 'provider' field
    let hasValidInput = false;
    
    inputs.forEach(input => {
      const value = input.value.trim();
      if (value) {
        // Map field names correctly for backend contract (snake_case)
        if (input.name === 'api_token') {
          data['api_key'] = value;  // Use snake_case api_key
        } else if (input.name === 'api_key') {
          data['api_key'] = value;
        } else if (input.name === 'api_secret') {
          data['api_secret'] = value;
        } else if (input.name === 'passphrase') {
          data['passphrase'] = value; // KuCoin requires passphrase
        } else if (input.name === 'sandbox' || input.name === 'paper') {
          data[input.name] = value === 'true' || value === true;
        } else {
          data[input.name] = value;
        }
        hasValidInput = true;
      }
    });

    // Validate that at least the primary API key is provided
    if (!hasValidInput || !data.api_key) {
      showNotification('Please enter a valid API key', 'error');
      return;
    }

    // Special validation for OpenAI
    if (provider === 'openai' && data.api_key && !data.api_key.startsWith('sk-')) {
      showNotification('Invalid OpenAI API key format (must start with sk-)', 'error');
      return;
    }

    // Validate exchange keys have secrets (except for some exchanges)
    if (EXCHANGES_NEEDING_SECRET.includes(provider.toLowerCase()) && !data.api_secret) {
      showNotification(`${provider.toUpperCase()} requires both API key and secret`, 'error');
      return;
    }

    // Validate KuCoin and Bitget passphrase requirement
    if (EXCHANGES_NEEDING_PASSPHRASE.includes(provider.toLowerCase()) && !data.passphrase) {
      showNotification(`${provider.toUpperCase()} requires passphrase`, 'error');
      return;
    }

    try {
      const response = await axios.post(`${API}/keys/save`, data, axiosConfig);
      showNotification(`✅ ${provider.toUpperCase()} API key saved!`);
      loadApiStatuses();
      
      // Clear form inputs after successful save
      inputs.forEach(input => input.value = '');
    } catch (err) {
      // Handle 500 errors with detailed debug information
      if (err.response?.status === 500) {
        const errorData = {
          endpoint: '/api/keys/save',
          provider: provider,
          statusCode: 500,
          message: err.response?.data?.detail || 'Internal server error',
          requestId: err.response?.headers?.['x-request-id'] || NOT_AVAILABLE
        };
        
        showNotification(
          `❌ Backend error saving key (500): ${errorData.message}. Check server logs.`,
          'error'
        );
        
        // Add a "Copy debug info" button via toast with longer duration
        console.error('API Key Save Error (500):', errorData);
        console.error('Debug Info (copy this):', JSON.stringify(errorData, null, 2));
      } else if (err.response?.status === 400) {
        showNotification(
          `❌ Invalid request (400): ${extractErrorMessage(err, 'Bad request')}`,
          'error'
        );
      } else {
        showNotification(extractErrorMessage(err, 'Failed to save API key'), 'error');
      }
      console.error('API key save error:', err);
    }
  };

  const handleTestApiKey = async (provider) => {
    try {
      // Backend expects provider field (not exchange)
      const response = await axios.post(`${API}/keys/test`, { 
        provider: provider.toLowerCase() 
      }, axiosConfig);
      
      showNotification(`✅ ${provider.toUpperCase()} connection verified!`);
      loadApiStatuses();
    } catch (err) {
      if (err.response?.status === 400) {
        showNotification(
          `❌ ${provider.toUpperCase()} test failed (400): ${extractErrorMessage(err, 'Invalid credentials format')}`,
          'error'
        );
      } else {
        showNotification(`❌ ${provider.toUpperCase()} connection failed: ${extractErrorMessage(err)}`, 'error');
      }
      console.error('API key test error:', err);
    }
  };

  const handleDeleteApiKey = async (provider) => {
    if (!window.confirm(`Remove ${provider} API keys?`)) return;
    
    try {
      await axios.delete(`${API}/keys/${provider}`, axiosConfig);
      
      // Immediately clear from state
      setApiKeys(prev => {
        const updated = { ...prev };
        delete updated[provider.toLowerCase()];
        return updated;
      });
      
      showNotification(`✅ ${provider} API removed`);
      
      // Reload to confirm
      setTimeout(() => loadApiStatuses(), 500);
    } catch (err) {
      showNotification('❌ Failed to remove API key', 'error');
    }
  };

  const getApiStatus = (provider) => {
    const key = apiKeys[provider.toLowerCase()];
    if (!key || key.status === 'not_configured') {
      return { badge: 'missing', text: 'Not configured', dot: 'err' };
    }
    if (key.status === 'configured_valid') {
      return { badge: 'verified', text: 'Tested OK', dot: 'ok' };
    }
    if (key.status === 'configured_invalid') {
      return { badge: 'error', text: 'Failed', dot: 'err' };
    }
    if (key.status === 'configured_untested') {
      return { badge: 'saved', text: 'Saved', dot: 'warn' };
    }
    return { badge: 'saved', text: 'Saved', dot: 'warn' };
  };

  const handleProfileChange = (field, value) => {
    setProfileData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleProfileSave = async () => {
    try {
      const updateData = {
        first_name: profileData.first_name,
        email: profileData.email,
        currency: profileData.currency
      };
      
      if (profileData.new_password) {
        updateData.new_password = profileData.new_password;
      }

      // Use PUT method and correct endpoint: /api/auth/profile
      await axios.put(`${API}/auth/profile`, updateData, axiosConfig);
      showNotification('Profile updated successfully!');
      
      // Update local user state
      setUser(prev => ({
        ...prev,
        first_name: profileData.first_name,
        email: profileData.email
      }));
      
      // Clear password field
      setProfileData(prev => ({
        ...prev,
        new_password: ''
      }));
    } catch (err) {
      showNotification(extractErrorMessage(err, 'Failed to update profile'), 'error');
      console.error('Profile update error:', err);
    }
  };

  const copyAddress = async (address) => {
    if (!address || address === NOT_AVAILABLE) {
      showNotification('No address available', 'error');
      return;
    }
    
    try {
      await navigator.clipboard.writeText(address);
      showNotification('Address copied to clipboard!');
    } catch (err) {
      console.error('Copy failed:', err);
      showNotification('Failed to copy address', 'error');
    }
  };

  const getAlertColor = (priority) => {
    switch (priority?.toLowerCase()) {
      case 'critical':
      case 'high':
        return 'var(--error)';
      case 'medium':
        return 'var(--accent2)';
      case 'low':
        return 'var(--success)';
      default:
        return 'var(--accent)';
    }
  };

  const handleTriggerBodyguard = async () => {
    try {
      setAiTaskLoading('bodyguard');
      showNotification('🛡️ AI Bodyguard scanning system...', 'info');
      setActiveSection('welcome'); // Switch to chat to see results
      
      const res = await axios.post(`${API}/autonomous/bodyguard/system-check`, {}, axiosConfig);
      const report = res.data;
      
      // Save status for display
      setBodyguardStatus(report);
      
      // Show detailed report in chat
      const message = `🛡️ AI Bodyguard System Scan Complete!\n\n` +
        `📊 Health Score: ${report.health_score}/100 (${report.health_status})\n` +
        `❌ Critical Issues: ${report.issues?.length || 0}\n` +
        `⚠️ Warnings: ${report.warnings?.length || 0}\n` +
        `✅ Passed Checks: ${report.passed_checks || 0}\n` +
        `⏱️ Scan Time: ${new Date().toLocaleTimeString()}\n\n` +
        (report.issues?.length > 0 ? `Issues Found:\n${report.issues.map(i => `• ${i}`).join('\n')}\n\n` : '') +
        (report.warnings?.length > 0 ? `Warnings:\n${report.warnings.map(w => `• ${w}`).join('\n')}\n\n` : '') +
        `💬 Ask me about any concerns or recommendations!`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      showNotification(
        `🛡️ Health: ${report.health_score}/100`,
        report.health_score >= 80 ? 'success' : 'warning'
      );
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Bodyguard check failed';
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Bodyguard scan failed: ${errorMsg}` 
      }]);
      showNotification(`❌ ${errorMsg}`, 'error');
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handleTriggerLearning = async () => {
    try {
      setAiTaskLoading('learning');
      showNotification('📚 AI Learning in progress...', 'info');
      setActiveSection('welcome'); // Switch to chat to see results
      
      const res = await axios.post(`${API}/autonomous/learning/trigger`, {}, axiosConfig);
      
      // Show detailed report in chat
      const report = res.data.report || {};
      const message = `📚 AI Learning Analysis Complete!\n\n` +
        `📊 Trades Analyzed: ${report.trades_analyzed || 0}\n` +
        `📈 Win Rate: ${report.win_rate || 0}%\n` +
        `💰 Avg Profit: R${report.avg_profit || 0}\n` +
        `🎯 Strategy Updates: ${report.updates || 'Optimized'}\n` +
        `⏱️ Completed: ${new Date().toLocaleTimeString()}\n\n` +
        `💬 Ask me any questions about this report!`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      showNotification('✅ AI Learning complete!', 'success');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Learning failed';
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Learning failed: ${errorMsg}` 
      }]);
      showNotification(`❌ ${errorMsg}`, 'error');
    } finally {
      setAiTaskLoading(null);
    }
  };

  // PHASE 10: Additional AI Tool Handlers
  const handleEvolveBots = async () => {
    try {
      setAiTaskLoading('evolve');
      toast.info('🧬 Evolving bots with genetic algorithm...');
      
      const result = await post('/bots/evolve', {});
      
      const message = `🧬 Bot Evolution Complete!\n\n` +
        `📊 Bots Evolved: ${result.evolved_count || 0}\n` +
        `📈 Performance Improvement: ${result.improvement || 0}%\n` +
        `🎯 New Strategies: ${result.new_strategies || 0}\n` +
        `⏱️ Completed: ${new Date().toLocaleTimeString()}\n\n` +
        `💬 Check your bots to see the improvements!`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      loadBots(); // Refresh bot list
      toast.success('✅ Bot evolution complete!');
    } catch (err) {
      const errorMsg = err.message || 'Bot evolution failed';
      if (errorMsg.includes('not configured')) {
        toast.error('Bot evolution not configured.');
      } else {
        toast.error(`❌ ${errorMsg}`);
      }
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Bot evolution failed: ${errorMsg}` 
      }]);
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handleGetInsights = async () => {
    try {
      setAiTaskLoading('insights');
      toast.info('🔮 Generating AI insights...');
      
      const result = await get('/ai/insights');
      
      const message = `🔮 Daily AI Insights\n\n` +
        `${result.insights || 'No insights available at this time.'}\n\n` +
        `⏱️ Generated: ${new Date().toLocaleTimeString()}`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      toast.success('✅ Insights generated!');
    } catch (err) {
      const errorMsg = err.message || 'Failed to get insights';
      toast.error(`❌ ${errorMsg}`);
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Insights failed: ${errorMsg}` 
      }]);
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handlePredictPrice = async () => {
    try {
      setAiTaskLoading('predict');
      toast.info('📊 Running ML price prediction...');
      
      const result = await get('/ml/predict?symbol=BTC-ZAR&platform=luno');
      
      const message = `📊 Price Prediction (BTC-ZAR)\n\n` +
        `💰 Current: R${result.current_price || NOT_AVAILABLE}\n` +
        `📈 Predicted (1h): R${result.prediction_1h || NOT_AVAILABLE}\n` +
        `📈 Predicted (24h): R${result.prediction_24h || NOT_AVAILABLE}\n` +
        `🎯 Confidence: ${result.confidence || NOT_AVAILABLE}%\n` +
        `⏱️ Generated: ${new Date().toLocaleTimeString()}\n\n` +
        `⚠️ This is not financial advice. Use for reference only.`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      toast.success('✅ Prediction complete!');
    } catch (err) {
      const errorMsg = err.message || 'Prediction failed';
      if (errorMsg.includes('not configured')) {
        toast.error('ML prediction not configured.');
      } else {
        toast.error(`❌ ${errorMsg}`);
      }
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Prediction failed: ${errorMsg}` 
      }]);
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handleReinvestProfits = async () => {
    if (!window.confirm('⚠️ This will automatically reinvest all profits. Continue?')) {
      return;
    }
    
    try {
      setAiTaskLoading('reinvest');
      toast.info('💰 Reinvesting profits...');
      
      const result = await post('/profits/reinvest', {});
      
      const message = `💰 Profit Reinvestment Complete!\n\n` +
        `💵 Amount Reinvested: R${result.amount || 0}\n` +
        `🤖 Bots Updated: ${result.bots_updated || 0}\n` +
        `📊 New Total Capital: R${result.new_total_capital || 0}\n` +
        `⏱️ Completed: ${new Date().toLocaleTimeString()}`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: message 
      }]);
      
      loadMetrics();
      loadBalances();
      toast.success('✅ Profits reinvested!');
    } catch (err) {
      const errorMsg = err.message || 'Reinvestment failed';
      toast.error(`❌ ${errorMsg}`);
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        type: 'system',
        content: `❌ Reinvestment failed: ${errorMsg}` 
      }]);
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handleEmailAllUsers = async () => {
    const subject = window.prompt('📧 Email Subject:');
    if (!subject) return;
    
    const message = window.prompt('📧 Email Message:');
    if (!message) return;
    
    if (!window.confirm(`Send to ALL users?\n\nSubject: ${subject}`)) return;
    
    try {
      setAiTaskLoading('email');
      const result = await post('/admin/email/broadcast', { subject, message });
      toast.success(`✅ Sent to ${result.sent || 0} users (${result.failed || 0} failed)`);
    } catch (err) {
      const errorMsg = err.message || 'Failed to send emails';
      toast.error(`❌ ${errorMsg}`);
    } finally {
      setAiTaskLoading(null);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      await axios.delete(`${API}/admin/users/${userId}`, axiosConfig);
      showNotification('User deleted successfully');
      loadAllUsers();
      loadSystemStats(); // Update stats
    } catch (err) {
      showNotification('Failed to delete user', 'error');
      console.error('Delete user error:', err);
    }
  };

  const handleBlockUser = async (userId, isBlocked) => {
    const action = isBlocked ? 'unblock' : 'block';
    if (!window.confirm(`Are you sure you want to ${action} this user?`)) {
      return;
    }

    try {
      await axios.put(`${API}/admin/users/${userId}/block`, 
        { blocked: !isBlocked }, 
        axiosConfig
      );
      showNotification(`User ${action}ed successfully`);
      loadAllUsers();
      loadSystemStats(); // Update stats
    } catch (err) {
      showNotification(`Failed to ${action} user`, 'error');
      console.error(`${action} user error:`, err);
    }
  };

  const handleChangePassword = async (userId) => {
    const newPassword = window.prompt('Enter new password for this user (minimum 6 characters):');
    if (!newPassword) {
      return;
    }

    if (newPassword.length < 6) {
      showNotification('Password must be at least 6 characters', 'error');
      return;
    }

    try {
      await axios.put(`${API}/admin/users/${userId}/password`, 
        { new_password: newPassword }, 
        axiosConfig
      );
      showNotification('Password changed successfully');
      loadAllUsers(); // Refresh user list after password change
    } catch (err) {
      showNotification('Failed to change password', 'error');
      console.error('Password change error:', err);
    }
  };



  // Load admin users with full details
  const loadAdminUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      const res = await axios.get(`${API}/admin/users`, axiosConfig);
      setAdminUsers(res.data.users || []);
    } catch (err) {
      showNotification('Failed to load users', 'error');
      console.error('Load admin users error:', err);
    } finally {
      setLoadingUsers(false);
    }
  }, [axiosConfig]);

  // Load all bots for admin control
  const loadAdminBots = useCallback(async () => {
    setLoadingBots(true);
    try {
      const res = await axios.get(`${API}/admin/bots`, axiosConfig);
      setAdminBots(res.data.bots || []);
    } catch (err) {
      showNotification('Failed to load bots', 'error');
      console.error('Load admin bots error:', err);
    } finally {
      setLoadingBots(false);
    }
  }, [axiosConfig]);

  const loadEmergencyOverrideStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/emergency-stop/status`, axiosConfig);
      setEmergencyOverrideStatus(res.data);
    } catch (err) {
      console.error('Emergency override status error:', err);
    }
  }, [axiosConfig]);

  const updateGlobalEmergencyOverride = async (disabled) => {
    const reason = window.prompt(disabled ? 'Reason for disabling emergency stop globally:' : 'Reason for re-enabling emergency stop globally:');
    if (!reason) return;
    await axios.post(`${API}/admin/emergency-stop/global`, { disabled, reason }, axiosConfig);
    showNotification('Global emergency-stop override updated', 'success');
    await loadEmergencyOverrideStatus();
    await loadRiskStatus();
  };

  const updateUserEmergencyOverride = async (targetUserId, disabled) => {
    if (!targetUserId) return;
    const reason = window.prompt(`${disabled ? 'Disable' : 'Re-enable'} emergency stop for user ${targetUserId}. Reason:`);
    if (!reason) return;
    await axios.post(`${API}/admin/emergency-stop/user`, { user_id: targetUserId, disabled, reason }, axiosConfig);
    showNotification('User emergency-stop override updated', 'success');
    await loadEmergencyOverrideStatus();
    await loadRiskStatus();
  };

  const clearUserEmergencyOverride = async (targetUserId) => {
    if (!targetUserId) return;
    await axios.post(`${API}/admin/emergency-stop/clear-user`, { user_id: targetUserId }, axiosConfig);
    showNotification('User emergency-stop override cleared', 'success');
    await loadEmergencyOverrideStatus();
    await loadRiskStatus();
  };

  // Load admin data when admin panel is shown
  useEffect(() => {
    if (showAdmin) {
      loadAllUsers();
      loadSystemStats();
      loadStorageData();
      loadAdminUsers();
      loadAdminBots();
      loadAdminHealth();
      loadEmergencyOverrideStatus();
    }
  }, [showAdmin, loadAllUsers, loadSystemStats, loadStorageData, loadAdminUsers, loadAdminBots, loadAdminHealth, loadEmergencyOverrideStatus]);

  useEffect(() => {
    if (!showAdmin) return undefined;
    const interval = setInterval(() => {
      loadSystemStats();
      loadAdminUsers();
      loadAdminBots();
      loadAdminHealth();
      loadEmergencyOverrideStatus();
    }, 15000);
    return () => clearInterval(interval);
  }, [showAdmin, loadSystemStats, loadAdminUsers, loadAdminBots, loadAdminHealth, loadEmergencyOverrideStatus]);

  // Handle user selection - filter bots for selected user
  const handleUserSelection = (userId) => {
    setSelectedUserId(userId);
    setSelectedBotId(''); // Reset bot selection when user changes
    
    if (userId) {
      // Filter bots for the selected user
      const userBots = adminBots.filter(bot => bot.user_id === userId);
      setFilteredAdminBots(userBots);
    } else {
      setFilteredAdminBots([]);
    }
  };

  // Reset user password
  const handleResetPassword = async (userId) => {
    const newPassword = window.prompt('Enter new password for this user (minimum 6 characters):');
    if (!newPassword) return;
    
    if (newPassword.length < 6) {
      showNotification('Password must be at least 6 characters', 'error');
      return;
    }

    setActionLoading(prev => ({ ...prev, [`reset-${userId}`]: true }));
    try {
      await axios.post(`${API}/admin/users/${userId}/reset-password`, 
        { new_password: newPassword }, 
        axiosConfig
      );
      showNotification('Password reset successfully', 'success');
    } catch (err) {
      showNotification('Failed to reset password', 'error');
      console.error('Reset password error:', err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`reset-${userId}`]: false }));
    }
  };

  // Block/Unblock user
  const handleToggleBlockUser = async (userId, currentStatus) => {
    const action = currentStatus === 'blocked' ? 'unblock' : 'block';
    if (!window.confirm(`Are you sure you want to ${action} this user?`)) return;

    setActionLoading(prev => ({ ...prev, [`block-${userId}`]: true }));
    try {
      await axios.post(`${API}/admin/users/${userId}/${action}`, {}, axiosConfig);
      showNotification(`User ${action}ed successfully`, 'success');
      loadAdminUsers();
    } catch (err) {
      showNotification(`Failed to ${action} user`, 'error');
      console.error(`${action} user error:`, err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`block-${userId}`]: false }));
    }
  };

  // Delete user
  const handleDeleteUserAdmin = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) return;

    setActionLoading(prev => ({ ...prev, [`delete-${userId}`]: true }));
    try {
      await axios.delete(`${API}/admin/users/${userId}`, axiosConfig);
      showNotification('User deleted successfully', 'success');
      loadAdminUsers();
    } catch (err) {
      showNotification('Failed to delete user', 'error');
      console.error('Delete user error:', err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`delete-${userId}`]: false }));
    }
  };

  // Force logout user
  const handleForceLogout = async (userId) => {
    if (!window.confirm('Force logout this user from all sessions?')) return;

    setActionLoading(prev => ({ ...prev, [`logout-${userId}`]: true }));
    try {
      await axios.post(`${API}/admin/users/${userId}/logout`, {}, axiosConfig);
      showNotification('User logged out successfully', 'success');
    } catch (err) {
      showNotification('Failed to logout user', 'error');
      console.error('Force logout error:', err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`logout-${userId}`]: false }));
    }
  };

  // Change bot mode
  const handleChangeBotMode = async (botId, newMode) => {
    if (!window.confirm(`Change bot trading mode to ${newMode}?`)) return;

    setActionLoading(prev => ({ ...prev, [`mode-${botId}`]: true }));
    try {
      await axios.post(`${API}/admin/bots/${botId}/mode`, 
        { mode: newMode }, 
        axiosConfig
      );
      showNotification(`Bot mode changed to ${newMode}`, 'success');
      await refreshBotState();
    } catch (err) {
      showNotification('Failed to change bot mode', 'error');
      console.error('Change bot mode error:', err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`mode-${botId}`]: false }));
    }
  };

  // Pause/Resume bot
  const handleToggleBotPause = async (botId, currentStatus) => {
    const action = currentStatus === 'active' ? 'pause' : 'resume';
    
    setActionLoading(prev => ({ ...prev, [`pause-${botId}`]: true }));
    try {
      await axios.post(`${API}/admin/bots/${botId}/${action}`, {}, axiosConfig);
      showNotification(`Bot ${action}d successfully`, 'success');
      await refreshBotState();
    } catch (err) {
      showNotification(`Failed to ${action} bot`, 'error');
      console.error(`${action} bot error:`, err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`pause-${botId}`]: false }));
    }
  };

  // Change bot exchange
  const handleChangeBotExchange = async (botId, newExchange) => {
    if (!window.confirm(`Change bot exchange to ${newExchange}?`)) return;

    setActionLoading(prev => ({ ...prev, [`exchange-${botId}`]: true }));
    try {
      await axios.post(`${API}/admin/bots/${botId}/exchange`, 
        { exchange: newExchange }, 
        axiosConfig
      );
      showNotification(`Bot exchange changed to ${newExchange}`, 'success');
      await refreshBotState();
    } catch (err) {
      showNotification('Failed to change bot exchange', 'error');
      console.error('Change bot exchange error:', err);
    } finally {
      setActionLoading(prev => ({ ...prev, [`exchange-${botId}`]: false }));
    }
  };

  const handleMigrateApiKeys = async () => {
    if (!window.confirm(
      'Migrate API keys from old JWT_SECRET-derived encryption to AMARKTAI_FERNET_KEY?\n\n' +
      'This will:\n' +
      '- Decrypt existing keys with old method\n' +
      '- Re-encrypt with new dedicated key\n' +
      '- Update all keys in database\n\n' +
      'Continue?'
    )) {
      return;
    }

    try {
      const response = await axios.post(
        `${API}/admin/migrate-api-keys`,
        {},
        axiosConfig
      );

      if (response.data.success) {
        const results = response.data.results;
        showNotification(
          `Migration completed! Migrated: ${results.migrated}, Failed: ${results.failed}, Skipped: ${results.skipped}`,
          results.failed > 0 ? 'warning' : 'success'
        );
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Unknown error';
      showNotification(`API Key migration failed: ${errorMsg}`, 'error');
      console.error('API Key migration error:', err);
    }
  };

  const modeLabel = systemModes.liveTrading ? 'LIVE' : 'PAPER';
  const modeTone = systemModes.liveTrading ? 'warning' : 'info';
  const realtimeConnected = connectionStatus.ws === 'Connected';
  const realtimeLabel = realtimeConnected ? 'Connected' : 'Reconnecting';
  const realtimeTone = realtimeConnected ? 'success' : 'warning';
  const riskLabel = riskStatus?.emergency_stop?.active
    ? 'Paused'
    : (riskStatus?.daily_loss_lock?.active || riskStatus?.bodyguard_lock?.active || riskStatus?.quarantine_active?.active)
      ? 'Guarded'
      : 'OK';
  const riskTone = riskLabel === 'OK' ? 'success' : riskLabel === 'Guarded' ? 'warning' : 'error';
  const userInitial = user?.first_name?.[0] || user?.email?.[0] || 'U';

  return {
    actionLoading,
    activeBotTab,
    activeSection,
    addCustomCountdown,
    adminApiHealth,
    adminBots,
    adminUsers,
    aiStatus,
    aiTaskLoading,
    allUsers,
    autoSpawnStatus,
    autonomyStatus,
    autopilotReinvestStatus,
    awaitingPassword,
    axiosConfig,
    balances,
    bodyguardStatus,
    botControlLoading,
    botDetailTab,
    botManagementTab,
    botSetup,
    botStatusFilter,
    bots,
    chatEndRef,
    chatInput,
    chatMessages,
    chatSending,
    clearUserEmergencyOverride,
    confirmLiveSwitch,
    connectionStatus,
    countdown,
    customCountdowns,
    deleteCustomCountdown,
    drawdownData,
    drawdownRange,
    editingBotId,
    editingBotName,
    eligibleBots,
    emergencyOverrideStatus,
    equityData,
    equityRange,
    executeEmergencyStop,
    filteredAdminBots,
    flokxAlerts,
    flokxStatus,
    formatDate,
    getAlertColor,
    graphPeriod,
    handleBlockUser,
    handleBotSetup,
    handleChangeBotExchange,
    handleChangeBotMode,
    handleChangePassword,
    handleChatKeyDown,
    handleClearChatHistory,
    handleCreateBot,
    handleCreateFlokxBot,
    handleCreateUAgent,
    handleDeleteBot,
    handleDeleteUser,
    handleDeleteUserAdmin,
    handleEmailAllUsers,
    handleEmergencyStop,
    handleEvolveBots,
    handleForceLogout,
    handleGetInsights,
    handleLogout,
    handleMigrateApiKeys,
    handlePaperReset,
    handlePredictPrice,
    handleProfileChange,
    handleProfileSave,
    handleReinvestProfits,
    handleRenameBotSubmit: handleSaveBotName,
    handleResetBodyguardLock,
    handleResetDailyLossLock,
    handleResetPassword,
    handleResumeAllBots,
    handleResumeBot,
    handleRiskProfileChange,
    handleSendMessage,
    handleStartBot,
    handleToggleBlockUser,
    handleToggleBotMode,
    handleToggleBotPause,
    handleTriggerBodyguard,
    handleTriggerLearning,
    handleUserSelection,
    isFlokxActive,
    isMobile,
    learningStatus,
    livePrices,
    loadAdminBots,
    loadAdminUsers,
    loadChatHistory,
    loadFlokxAlerts,
    loadingBots,
    loadingUsers,
    metrics,
    metricsTab,
    modeLabel,
    modeTone,
    newCountdownAmount,
    newCountdownLabel,
    overviewData,
    paperResetError,
    paperResetLoading,
    platformFilter,
    profileData,
    profitData,
    profitsTab,
    realtimeConnected,
    realtimeLabel,
    realtimeTone,
    recentTrades,
    riskLabel,
    riskProfile,
    riskStatus,
    riskTone,
    selectedBotDetailId,
    selectedBotId,
    selectedTradeId,
    selectedUserId,
    setActiveBotTab,
    setActiveSection,
    setBotDetailTab,
    setBotManagementTab,
    setBotSetup,
    setBotStatusFilter,
    setChatInput,
    setChatMessages,
    setDrawdownRange,
    setEditingBotId,
    setEditingBotName,
    setEquityRange,
    setGraphPeriod,
    setMetricsTab,
    setNewCountdownAmount,
    setNewCountdownLabel,
    setPaperResetError,
    setPlatformFilter,
    setProfitsTab,
    setSelectedBotDetailId,
    setSelectedBotId,
    setSelectedTradeId,
    setSelectedUserId,
    setShowAITools,
    setShowAddCountdown,
    setShowEmergencyConfirm,
    setShowPaperResetModal,
    setShowPromotionModal,
    setTradeBotFilter,
    setTradeExchangeFilter,
    setTradePairFilter,
    setWinRatePeriod,
    showAITools,
    showAddCountdown,
    showAdmin,
    showEmergencyConfirm,
    showNotification,
    showPaperResetModal,
    showPromotionModal,
    showSection,
    storageData,
    storageError,
    storageTotals,
    systemModes,
    systemStats,
    toggleSystemMode,
    tradeBotFilter,
    tradeExchangeFilter,
    tradePairFilter,
    updateGlobalEmergencyOverride,
    updateUserEmergencyOverride,
    user,
    userInitial,
    winRateData,
    winRatePeriod
  };
}
