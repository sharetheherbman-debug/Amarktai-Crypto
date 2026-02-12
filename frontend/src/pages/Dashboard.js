import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import './DashboardV3.css';
import WalletHub from '../components/WalletHub';
import WalletOverview from '../components/WalletOverview';
import APIKeySettings from '../components/APIKeySettings';
import PlatformSelector from '../components/PlatformSelector';
import ErrorBoundary from '../components/ErrorBoundary';
import BotQuarantineSection from '../components/Dashboard/BotQuarantineSection';
import BotTrainingSection from '../components/Dashboard/BotTrainingSection';
import TrainingQuarantineSection from '../components/Dashboard/TrainingQuarantineSection';
import { API_BASE, wsUrl } from '../lib/api.js';
import { formatTimestamp } from '../utils/time.js';
import { useRealtimeEvent } from '../hooks/useRealtime';
import { useDashboardData, normalizeLivePrices, getBotStatus } from '../hooks/useDashboardData';
import { post, get } from '../lib/apiClient';
import realtimeClient from '../lib/realtime';
import { getAllExchanges, getActiveExchanges, getExchangeById, FEATURE_FLAGS } from '../config/exchanges';
import { SUPPORTED_PLATFORMS, PLATFORM_CONFIG, getPlatformDisplayName, getPlatformIcon } from '../constants/platforms';
import VersionBadge from '../components/VersionBadge';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const API = API_BASE;
// Admin password is verified on backend only - no hardcoded password in frontend
// Backend validates against ADMIN_PASSWORD environment variable
const APP_VERSION = '1.0.6'; // Increment this to force cache clear

// TASK D - Exchanges that require additional fields
const EXCHANGES_NEEDING_SECRET = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];
const EXCHANGES_NEEDING_PASSPHRASE = ['kucoin', 'bitget'];

const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const resolveSystemMode = (modeRes) => {
  if (!modeRes) return 'paper';
  return modeRes.mode || (modeRes.liveTrading ? 'live' : modeRes.autopilot ? 'autonomous' : 'paper');
};

const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

const safePercent = (value, digits = 1, fallback = '0.0') => `${safeToFixed(value, digits, fallback)}%`;

export default function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [activeSection, setActiveSection] = useState('welcome');
  const [intelligenceTab, setIntelligenceTab] = useState('whale-flow'); // Tab state for Intelligence section
  const [metricsTab, setMetricsTab] = useState('flokx'); // Tab state for Metrics section - default to Flokx Alerts
  const [botManagementTab, setBotManagementTab] = useState('creation'); // Tab state for Bot Management parent section
  const [profitsTab, setProfitsTab] = useState('metrics'); // Tab state for Profits & Performance parent section
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
  const [bots, setBots] = useState([]);
  const [apiKeys, setApiKeys] = useState({});
  const [metrics, setMetrics] = useState({
    totalProfit: 'R0.00',
    activeBots: '0 / 0',
    exposure: '0%',
    riskLevel: 'Unknown',
    aiSentiment: 'Neutral',
    lastUpdate: '—'
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
  const [expandedBots, setExpandedBots] = useState({});
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
  const [wsRtt, setWsRtt] = useState('—');
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
    status: 'Unknown',
    errors: 0,
    uptime: '—',
    lastCheck: '—'
  });
  const [overviewData, setOverviewData] = useState({
    totalProfit: 0,
    todaysProfit: 0,
    totalTrades: 0,
    winRate: 0,
    activeBots: 0,
    pausedBots: 0,
    paperWalletTotal: 0,
    paperWalletAllocated: 0,
    lastTradeTime: null,
    systemMode: 'paper'
  });
  const [botControlLoading, setBotControlLoading] = useState({});
  const [recentTrades, setRecentTrades] = useState([]);
  const [bodyguardStatus, setBodyguardStatus] = useState(null);
  // Consolidated risk status from /api/risk/status
  const [riskStatus, setRiskStatus] = useState(null);
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
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminBots, setAdminBots] = useState([]);
  const [adminApiHealth, setAdminApiHealth] = useState({ status: 'Unknown', lastCheck: null, error: null });
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingBots, setLoadingBots] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedBotId, setSelectedBotId] = useState('');
  const [filteredAdminBots, setFilteredAdminBots] = useState([]);
  
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
    if (!dateStr) return '—';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return '—';
      
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
      return '—';
    }
  };

  const formatDuration = (seconds) => {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—';
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
      
      // Update live prices every 5 seconds
      const priceInterval = setInterval(() => {
        loadLivePrices();
      }, 5000);
      
      return () => {
        clearInterval(priceInterval);
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
      const data = await get('/ai/chat/history?days=30&limit=100');
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
      await post('/ai/chat/clear', {});
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
          setWsRtt('—');
          
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
      const [snapshotResult, paperWalletResult, modeResult, tradesResult] = await Promise.allSettled([
        get('/overview/snapshot'),
        get('/wallet/paper'),
        get('/system/mode'),
        get('/trades/recent?limit=1')
      ]);

      const snapshotRes = snapshotResult.status === 'fulfilled' ? snapshotResult.value : {};
      const paperWalletRes = paperWalletResult.status === 'fulfilled' ? paperWalletResult.value : {};
      const modeRes = modeResult.status === 'fulfilled' ? modeResult.value : {};
      const tradesRes = tradesResult.status === 'fulfilled' ? tradesResult.value : {};

      const totalProfit = safeNumber(snapshotRes?.total_profit, 0);
      const todaysProfit = safeNumber(snapshotRes?.today_profit, 0);
      const totalTrades = safeNumber(snapshotRes?.trades_total, 0);
      const winRate = safeNumber(snapshotRes?.win_rate, 0);
      const activeBots = safeNumber(snapshotRes?.bots_active, 0);
      const pausedBots = safeNumber(snapshotRes?.bots_paused, 0);
      const paperWalletTotal = safeNumber(paperWalletRes?.total, 0);
      const paperWalletAllocated = Object.values(paperWalletRes?.allocated || {}).reduce(
        (sum, value) => sum + safeNumber(value, 0),
        0
      );
      const systemMode = resolveSystemMode(modeRes);
      const lastTradeTime = tradesRes?.trades?.[0]?.timestamp || null;

      setOverviewData({
        totalProfit,
        todaysProfit,
        totalTrades,
        winRate,
        activeBots,
        pausedBots,
        paperWalletTotal,
        paperWalletAllocated,
        lastTradeTime,
        systemMode
      });
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
    }
  };

  const loadAutoSpawnStatus = async () => {
    try {
      const res = await get('/diagnostics/auto-spawn');
      setAutoSpawnStatus(res);
    } catch (err) {
      console.error('Auto-spawn status fetch error:', err);
      setAutoSpawnStatus(null);
    }
  };

  const loadAutopilotGrowthStatus = async () => {
    try {
      const res = await axios.get(`${API}/autopilot/growth/status`, axiosConfig);
      setAutopilotGrowthStatus(res.data);
    } catch (err) {
      console.error('Autopilot growth status fetch error:', err);
      setAutopilotGrowthStatus(null);
    }
  };

  const loadAutopilotReinvestStatus = async () => {
    try {
      const res = await axios.get(`${API}/autopilot/reinvest/status`, axiosConfig);
      setAutopilotReinvestStatus(res.data);
    } catch (err) {
      console.error('Autopilot reinvest status fetch error:', err);
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
      setRecentTrades(res.data.trades || []);
    } catch (err) {
      console.error('Recent trades fetch error:', err);
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
        lastUpdate: new Date().toLocaleTimeString() || '—'
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
        uptime: data.uptime || '—',
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
        uptime: '—',
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
    const originalInput = chatInput.trim();
    if (!originalInput) return;

    const userMsg = { role: 'user', content: originalInput };
    setChatMessages(prev => [...prev, userMsg]);
    const msgLower = originalInput.toLowerCase(); // Case-insensitive for command matching
    setChatInput('');

    // PHASE 12: Save user message to backend
    try {
      await post('/ai/chat', {
        role: 'user',
        content: originalInput,
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
            const successMsg = { role: 'assistant', content: '✅ Admin panel unlocked successfully! Switching to admin section...' };
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
          const successMsg = { role: 'assistant', content: '✅ Admin panel hidden successfully.' };
          setChatMessages(prev => [...prev, successMsg]);
          console.log('Admin section deactivated, showAdmin:', false);
          
          // Save success message
          try {
            await post('/ai/chat', {
              role: 'assistant',
              content: successMsg.content,
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
          metadata: { timestamp: new Date().toISOString() }
        });
      } catch (error) {
        console.error('Failed to save assistant message:', error);
      }
      
      return;
    }

    // Send all other messages to AI backend
    try {
      const res = await axios.post(`${API}/ai/chat`, { message: originalInput, context: 'dashboard' }, axiosConfig);
      const payload = res.data || {};
      if (payload?.success === false || payload?.error) {
        const errorContent = payload?.content || payload?.error || payload?.detail || 'AI chat error.';
        setChatMessages(prev => [...prev, { role: 'assistant', content: errorContent, error: true }]);
        return;
      }
      const reply = typeof payload === 'string'
        ? payload
        : (payload.content || payload.response || payload.reply || payload.message || 'No response');
      const assistantMsg = { role: 'assistant', content: reply };
      setChatMessages(prev => [...prev, assistantMsg]);
      
      // PHASE 12: Save assistant message to backend
      try {
        await post('/ai/chat', {
          role: 'assistant',
          content: reply,
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
          metadata: { timestamp: new Date().toISOString(), error: true }
        });
      } catch (error) {
        console.error('Failed to save error message:', error);
      }
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

  const handleEmergencyStop = async () => {
    if (!window.confirm('🚨 EMERGENCY STOP: This will immediately stop ALL bots and trading activity. Continue?')) {
      return;
    }
    
    try {
      await axios.post(`${API}/system/emergency-stop`, {}, axiosConfig);
      showNotification('🚨 EMERGENCY STOP ACTIVATED - All systems halted', 'error');
      setSystemModes({ paperTrading: false, liveTrading: false, autopilot: false });
      loadBots();
    } catch (err) {
      console.error('Emergency stop error:', err);
      showNotification('Emergency stop failed', 'error');
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

  const toggleBotExpand = (botId) => {
    setExpandedBots(prev => ({ ...prev, [botId]: !prev[botId] }));
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
          requestId: err.response?.headers?.['x-request-id'] || 'N/A'
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
      return { badge: 'verified', text: 'Valid ✓', dot: 'ok' };
    }
    if (key.status === 'configured_invalid') {
      return { badge: 'error', text: 'Invalid ✗', dot: 'err' };
    }
    if (key.status === 'configured_untested') {
      return { badge: 'saved', text: 'Configured (untested)', dot: 'warn' };
    }
    return { badge: 'saved', text: 'Configured', dot: 'warn' };
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
    if (!address || address === 'N/A') {
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
        return '#f59e0b';
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
        content: message 
      }]);
      
      showNotification('✅ AI Learning complete!', 'success');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Learning failed';
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
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
        content: message 
      }]);
      
      toast.success('✅ Insights generated!');
    } catch (err) {
      const errorMsg = err.message || 'Failed to get insights';
      toast.error(`❌ ${errorMsg}`);
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
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
        `💰 Current: R${result.current_price || 'N/A'}\n` +
        `📈 Predicted (1h): R${result.prediction_1h || 'N/A'}\n` +
        `📈 Predicted (24h): R${result.prediction_24h || 'N/A'}\n` +
        `🎯 Confidence: ${result.confidence || 'N/A'}%\n` +
        `⏱️ Generated: ${new Date().toLocaleTimeString()}\n\n` +
        `⚠️ This is not financial advice. Use for reference only.`;
      
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
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

  // Load admin data when admin panel is shown
  useEffect(() => {
    if (showAdmin) {
      loadAllUsers();
      loadSystemStats();
      loadStorageData();
      loadAdminUsers();
      loadAdminBots();
      loadAdminHealth();
    }
  }, [showAdmin, loadAllUsers, loadSystemStats, loadStorageData, loadAdminUsers, loadAdminBots, loadAdminHealth]);

  useEffect(() => {
    if (!showAdmin) return undefined;
    const interval = setInterval(() => {
      loadSystemStats();
      loadAdminUsers();
      loadAdminBots();
      loadAdminHealth();
    }, 15000);
    return () => clearInterval(interval);
  }, [showAdmin, loadSystemStats, loadAdminUsers, loadAdminBots, loadAdminHealth]);

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

  const renderWelcome = () => (
    <section className="section active">
      <div className="card welcome-container">
        <div className="welcome-header">
          <h2 style={{color: '#ffffff'}}>Welcome, {user?.first_name || 'User'}</h2>
          <p>Control your AI trading system with natural language.</p>
        </div>
        
        {/* AI Tools Toggle Button */}
        <div style={{marginBottom: '16px'}}>
          <button 
            onClick={() => setShowAITools(!showAITools)}
            style={{
              width: '100%',
              padding: '12px 16px',
              background: showAITools ? 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)' : 'var(--panel)',
              color: showAITools ? 'white' : 'var(--text)',
              border: '1px solid var(--success)',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.95rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>🧠 AI Tools & Analytics</span>
            <span>{showAITools ? '▼' : '▶'}</span>
          </button>
        </div>
        
        {/* AI Tools & Analytics - Collapsible */}
        {showAITools && (
        <div style={{marginBottom: '20px', padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--success)'}}>
          <p style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '12px'}}>
            ⚡ All reports appear in the chat below. Ask questions about results!
          </p>
          
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
            <button
              onClick={handleTriggerLearning}
              disabled={aiTaskLoading === 'learning'}
              style={{padding: '12px', background: aiTaskLoading === 'learning' ? '#666' : 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)', color: 'white', border: 'none', borderRadius: '6px', cursor: aiTaskLoading === 'learning' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'learning' ? 0.7 : 1}}
            >
              {aiTaskLoading === 'learning' ? '⏳ Analyzing...' : '📚 AI Learning'}
            </button>
            
            <button 
              onClick={handleEvolveBots}
              disabled={aiTaskLoading === 'evolve'}
              style={{padding: '12px', background: aiTaskLoading === 'evolve' ? '#666' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)', color: 'white', border: 'none', borderRadius: '6px', cursor: aiTaskLoading === 'evolve' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'evolve' ? 0.7 : 1}}
            >
              {aiTaskLoading === 'evolve' ? '⏳ Evolving...' : '🧬 Evolve Bots'}
            </button>
            
            <button 
              onClick={handleGetInsights}
              disabled={aiTaskLoading === 'insights'}
              style={{padding: '12px', background: aiTaskLoading === 'insights' ? '#666' : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)', color: 'white', border: 'none', borderRadius: '6px', cursor: aiTaskLoading === 'insights' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'insights' ? 0.7 : 1}}
            >
              {aiTaskLoading === 'insights' ? '⏳ Generating...' : '💡 AI Insights'}
            </button>
            
            <button 
              onClick={handlePredictPrice}
              disabled={aiTaskLoading === 'predict'}
              style={{padding: '12px', background: aiTaskLoading === 'predict' ? '#666' : 'linear-gradient(135deg, #ec4899 0%, #db2777 100%)', color: 'white', border: 'none', borderRadius: '6px', cursor: aiTaskLoading === 'predict' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'predict' ? 0.7 : 1}}
            >
              {aiTaskLoading === 'predict' ? '⏳ Predicting...' : '🔮 ML Predict'}
            </button>
            
            <button 
              onClick={handleReinvestProfits}
              disabled={aiTaskLoading === 'reinvest'}
              style={{padding: '12px', background: aiTaskLoading === 'reinvest' ? '#666' : 'linear-gradient(135deg, #14b8a6 0%, #0d9488 100%)', color: 'white', border: 'none', borderRadius: '6px', cursor: aiTaskLoading === 'reinvest' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'reinvest' ? 0.7 : 1}}
            >
              {aiTaskLoading === 'reinvest' ? '⏳ Reinvesting...' : '💰 Reinvest Profits'}
            </button>
          </div>
        </div>
        )}
        
        <div className="amk-chat">
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px'}}>
            <button
              onClick={loadChatHistory}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                background: '#3b82f6',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              📜 Load History
            </button>
            <button
              onClick={handleClearChatHistory}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                background: '#ef4444',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              🗑️ Clear History
            </button>
          </div>
          <div className="amk-chat-box">
            {chatMessages.map((msg, idx) => (
              <div key={idx} className={`msg ${msg.role}`}>
                <div className="bubble">{msg.content}</div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
          <div className="amk-row">
            <input
              type={awaitingPassword ? "password" : "text"}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder={awaitingPassword ? "Enter admin password..." : "Type a message or ask about AI reports..."}
            />
            <button className="send" onClick={handleSendMessage}>Send</button>
          </div>
        </div>
      </div>
    </section>
  );

  const renderOverview = () => (
    <section className="section active">
      <div className="card">
        <h2 style={{color: '#ffffff'}}>System Overview</h2>
        
        {/* Risk Status Banner */}
        {riskStatus?.emergency_stop?.active && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
            border: '2px solid #b91c1c',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
          }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🚨 Emergency Stop Active — Trading Disabled
            </div>
            <div style={{fontSize: '0.9rem', marginBottom: '8px'}}>
              <strong>Reason:</strong> {riskStatus.emergency_stop.reason || 'Emergency stop is active'}
            </div>
            {riskStatus.emergency_stop.next_action && (
              <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
                Next action: {riskStatus.emergency_stop.next_action}
              </div>
            )}
          </div>
        )}
        {riskStatus?.daily_loss_lock?.active && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
            border: '2px solid #dc2626',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
            }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🛡️ Daily Loss Lock Active — Bots Paused for Protection
            </div>
            <div style={{fontSize: '0.9rem', marginBottom: '8px'}}>
              <strong>Reason:</strong> {riskStatus.daily_loss_lock.reason || 'Risk threshold exceeded'}
            </div>
            <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
              Locked at: {formatDate(riskStatus.daily_loss_lock.locked_at)}
            </div>
            {riskStatus.daily_loss_lock.next_action && (
              <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
                Next action: {riskStatus.daily_loss_lock.next_action}
              </div>
            )}
            {user?.is_admin && (
              <div style={{marginTop: '12px', display: 'flex', gap: '10px'}}>
                <button
                  onClick={handleResetDailyLossLock}
                  style={{
                    padding: '10px 16px',
                    background: 'white',
                    color: '#dc2626',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  🔓 Reset Daily Loss Lock
                </button>
                <button
                  onClick={handleResumeAllBots}
                  disabled={botControlLoading['all']}
                  style={{
                    padding: '10px 16px',
                    background: 'rgba(255,255,255,0.2)',
                    color: 'white',
                    border: '1px solid white',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: botControlLoading['all'] ? 'wait' : 'pointer',
                    opacity: botControlLoading['all'] ? 0.6 : 1
                  }}
                >
                  {botControlLoading['all'] ? '⏳ Resuming...' : '▶️ Resume All Bots'}
                </button>
              </div>
            )}
            {!user?.is_admin && (
              <div style={{marginTop: '12px', fontSize: '0.85rem', fontStyle: 'italic'}}>
                Admin access required to reset risk lock
              </div>
            )}
          </div>
        )}

        {(riskStatus?.bodyguard_lock?.active || riskStatus?.quarantine_active?.active) && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
            border: '2px solid #d97706',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
          }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🛡️ Bodyguard/Quarantine Lock Active
            </div>
            {riskStatus?.bodyguard_lock?.active && (
              <div style={{fontSize: '0.9rem', marginBottom: '6px'}}>
                <strong>Bodyguard:</strong> {riskStatus.bodyguard_lock.reason || 'Bots paused by bodyguard'}
              </div>
            )}
            {riskStatus?.quarantine_active?.active && (
              <div style={{fontSize: '0.9rem', marginBottom: '6px'}}>
                <strong>Quarantine:</strong> {riskStatus.quarantine_active.reason || 'Bots quarantined for retraining'}
              </div>
            )}
            {user?.is_admin ? (
              <div style={{marginTop: '12px', display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
                <button
                  onClick={handleResetBodyguardLock}
                  style={{
                    padding: '10px 16px',
                    background: 'white',
                    color: '#d97706',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  🔓 Reset Bodyguard Locks
                </button>
              </div>
            ) : (
              <div style={{marginTop: '12px', fontSize: '0.85rem', fontStyle: 'italic'}}>
                Admin access required to reset bodyguard locks
              </div>
            )}
          </div>
        )}
        
        {/* Overview Container with Image and Enhanced Metrics Panel */}
        <div className="overview-container">
          <div className="overview-image">
            <img src="/assets/poster.jpg" alt="Amarktai humanoid trading bot poster" />
          </div>
          <div className="overview-metrics">
            <div className="status-list">
              {/* System Status Metrics */}
              <div className="status-item">
                <strong>Total Profit</strong>
                <div className="led-row">
                  <span style={{color: safeNumber(overviewData.totalProfit, 0) >= 0 ? 'var(--success)' : 'var(--error)'}}>
                    R{safeToFixed(overviewData.totalProfit, 2)}
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>Today's Profit</strong>
                <div className="led-row">
                  <span style={{color: safeNumber(overviewData.todaysProfit, 0) >= 0 ? 'var(--success)' : 'var(--error)'}}>
                    R{safeToFixed(overviewData.todaysProfit, 2)}
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>Total Trades</strong>
                <div className="led-row"><span>{safeNumber(overviewData.totalTrades, 0)}</span></div>
              </div>
              <div className="status-item">
                <strong>Win Rate</strong>
                <div className="led-row"><span>{safeToFixed(overviewData.winRate, 1, '0.0')}%</span></div>
              </div>
              <div className="status-item">
                <strong>Bot Status</strong>
                <div className="led-row">
                  <span style={{color: 'var(--success)'}}>{safeNumber(overviewData.activeBots, 0)} Active</span>
                  <span style={{color: 'var(--muted)', margin: '0 4px'}}>/</span>
                  <span style={{color: 'var(--error)'}}>{safeNumber(overviewData.pausedBots, 0)} Paused</span>
                </div>
              </div>
              <div className="status-item">
                <strong>Paper Wallet Total</strong>
                <div className="led-row">
                  <span>R{safeToFixed(overviewData.paperWalletTotal, 2)}</span>
                </div>
              </div>
              <div className="status-item">
                <strong>Allocated to Bots</strong>
                <div className="led-row">
                  <span>R{safeToFixed(overviewData.paperWalletAllocated, 2)}</span>
                </div>
              </div>
              <div className="status-item">
                <strong>System Mode</strong>
                <div className="led-row">
                  <span style={{textTransform: 'uppercase', fontWeight: 700}}>
                    {overviewData.systemMode === 'live' && '🔴 LIVE'}
                    {overviewData.systemMode === 'autonomous' && '🤖 AUTONOMOUS'}
                    {overviewData.systemMode === 'paper' && '📄 PAPER'}
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>Last Trade</strong>
                <div className="led-row">
                  <span style={{fontSize: '0.85rem'}}>
                    {formatDate(overviewData.lastTradeTime) !== '—' ? formatDate(overviewData.lastTradeTime) : 'No trades yet'}
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>Bodyguard Status</strong>
                <div className="led-row">
                  {riskStatus?.bodyguard_lock?.active ? (
                    <span style={{color: 'var(--error)', fontWeight: 700}}>🔒 LOCKED</span>
                  ) : (
                    <span style={{color: 'var(--success)', fontWeight: 700}}>✅ CLEAR</span>
                  )}
                </div>
              </div>

              {/* Existing metrics */}
              <div className="status-item">
                <strong>Exposure</strong>
                <div className="led-row"><span>{metrics.exposure}</span></div>
              </div>
              <div className="status-item">
                <strong>Risk Level</strong>
                <div className="led-row"><span>{metrics.riskLevel}</span></div>
              </div>
              <div className="status-item">
                <strong>AI Sentiment</strong>
                <div className="led-row"><span>{metrics.aiSentiment}</span></div>
              </div>
              <div className="status-item">
                <strong>Last Update</strong>
                <div className="led-row"><span>{metrics.lastUpdate}</span></div>
              </div>
              <div className="status-item">
                <strong>Round-Trip Time</strong>
                <div className="led-row"><span>{wsRtt}</span></div>
              </div>
              <div className="status-item">
                <strong>WebSocket</strong>
                <div className="led-row">
                  <span style={{color: connectionStatus.ws === 'Connected' ? 'var(--success)' : 'var(--error)'}}>
                    {connectionStatus.ws}
                  </span>
                  <div className={`status-dot ${connectionStatus.ws === 'Connected' ? 'ok' : 'err'}`}></div>
                </div>
              </div>
              <div className="status-item">
                <strong>Live Updates</strong>
                <div className="led-row">
                  <span style={{color: connectionStatus.sse === 'Connected' ? 'var(--success)' : 'var(--error)'}}>
                    {connectionStatus.sse}
                  </span>
                  <div className={`status-dot ${connectionStatus.sse === 'Connected' ? 'ok' : 'err'}`}></div>
                </div>
              </div>
              <div className="status-item">
                <strong>BTC/ZAR</strong>
                <div className="led-row">
                  <span>R{safeNumber(livePrices['BTC/ZAR']?.price, 0).toLocaleString()}</span>
                  {livePrices['BTC/ZAR']?.isFallback && (
                    <span style={{
                      fontSize: '0.65rem',
                      padding: '2px 6px',
                      marginLeft: '8px',
                      background: 'rgba(59, 130, 246, 0.2)',
                      color: '#3b82f6',
                      borderRadius: '4px',
                      fontWeight: '600'
                    }}>
                      Public data
                    </span>
                  )}
                  <span style={{
                    color: livePrices['BTC/ZAR']?.change >= 0 ? 'var(--success)' : 'var(--error)',
                    fontSize: '0.8rem',
                    marginLeft: '8px'
                  }}>
                    {livePrices['BTC/ZAR']?.change >= 0 ? '+' : ''}{safeToFixed(livePrices['BTC/ZAR']?.change, 2)}%
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>ETH/ZAR</strong>
                <div className="led-row">
                  <span>R{safeNumber(livePrices['ETH/ZAR']?.price, 0).toLocaleString()}</span>
                  {livePrices['ETH/ZAR']?.isFallback && (
                    <span style={{
                      fontSize: '0.65rem',
                      padding: '2px 6px',
                      marginLeft: '8px',
                      background: 'rgba(59, 130, 246, 0.2)',
                      color: '#3b82f6',
                      borderRadius: '4px',
                      fontWeight: '600'
                    }}>
                      Public data
                    </span>
                  )}
                  <span style={{
                    color: livePrices['ETH/ZAR']?.change >= 0 ? 'var(--success)' : 'var(--error)',
                    fontSize: '0.8rem',
                    marginLeft: '8px'
                  }}>
                    {livePrices['ETH/ZAR']?.change >= 0 ? '+' : ''}{safeToFixed(livePrices['ETH/ZAR']?.change, 2)}%
                  </span>
                </div>
              </div>
              <div className="status-item">
                <strong>XRP/ZAR</strong>
                <div className="led-row">
                  <span>R{safeNumber(livePrices['XRP/ZAR']?.price, 0).toLocaleString()}</span>
                  {livePrices['XRP/ZAR']?.isFallback && (
                    <span style={{
                      fontSize: '0.65rem',
                      padding: '2px 6px',
                      marginLeft: '8px',
                      background: 'rgba(59, 130, 246, 0.2)',
                      color: '#3b82f6',
                      borderRadius: '4px',
                      fontWeight: '600'
                    }}>
                      Public data
                    </span>
                  )}
                  <span style={{
                    color: livePrices['XRP/ZAR']?.change >= 0 ? 'var(--success)' : 'var(--error)',
                    fontSize: '0.8rem',
                    marginLeft: '8px'
                  }}>
                    {livePrices['XRP/ZAR']?.change >= 0 ? '+' : ''}{safeToFixed(livePrices['XRP/ZAR']?.change, 2)}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
    </section>
  );

  const renderApiSetup = () => {
    // Build providers list dynamically from exchange config
    const exchanges = getAllExchanges();
    const exchangeProviders = exchanges.map(ex => ex.id);
    const otherProviders = ['openai', 'flokx', 'fetchai'];
    const providers = [...otherProviders, ...exchangeProviders];
    
    return (
      <section className="section active">
        <div className="card">
          <h2 style={{color: '#ffffff'}}>🔑 API Setup - All Integration Keys</h2>
          <p style={{color: 'var(--muted)', marginBottom: '20px', fontSize: '0.9rem'}}>
            Configure all API keys and credentials for exchanges, AI services, and integrations. All keys are encrypted and stored securely per-user.
          </p>
          <div className="api-accordion">
            {providers.map(provider => {
              const status = getApiStatus(provider);
              const isExpanded = expandedApis[provider];
              const exchangeInfo = getExchangeById(provider);
              
              return (
                <div key={provider} className="api-card">
                  <div className="api-header" onClick={() => toggleApiExpand(provider)}>
                    <span>
                      {exchangeInfo ? `${exchangeInfo.icon} ${exchangeInfo.displayName}` : provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </span>
                    <div style={{display: 'flex', alignItems: 'center', gap: '6px'}}>
                      <span className={`status-badge ${status.badge}`}>{status.text}</span>
                      <div className={`status-dot ${status.dot}`}></div>
                    </div>
                  </div>
                  <div className={`api-form ${isExpanded ? 'active' : ''}`} id={`form-${provider}`}>
                    {/* TASK D - Config-driven field schema (no duplication) */}
                    {provider === 'openai' && (
                      <input name="api_key" placeholder="API Key (sk-...)" type="password" />
                    )}
                    {provider === 'flokx' && (
                      <input name="api_token" placeholder="API Token" type="password" />
                    )}
                    {provider === 'fetchai' && (
                      <input name="api_key" placeholder="API Key" type="password" />
                    )}
                    {/* All exchanges require api_key + api_secret */}
                    {SUPPORTED_PLATFORMS.includes(provider) && (
                      <>
                        <input 
                          name="api_key" 
                          placeholder="API Key" 
                          type="text"
                          style={{ color: '#e0e0e0', backgroundColor: 'rgba(255,255,255,0.05)' }}
                        />
                        <input 
                          name="api_secret" 
                          placeholder="Secret Key" 
                          type="password"
                          style={{ color: '#e0e0e0', backgroundColor: 'rgba(255,255,255,0.05)' }}
                        />
                        {/* KuCoin and Bitget require passphrase */}
                        {(provider === 'kucoin' || provider === 'bitget') && (
                          <input 
                            name="passphrase" 
                            placeholder="Passphrase" 
                            type="text"
                            style={{ color: '#e0e0e0', backgroundColor: 'rgba(255,255,255,0.05)' }}
                          />
                        )}
                      </>
                    )}
                    <div className="buttons">
                      <button 
                        onClick={() => handleSaveApiKey(provider)}
                        disabled={exchangeInfo?.comingSoon}
                        style={{ opacity: exchangeInfo?.comingSoon ? 0.5 : 1 }}
                      >
                        Save
                      </button>
                      <button 
                        onClick={() => handleTestApiKey(provider)}
                        disabled={exchangeInfo?.comingSoon}
                        style={{ opacity: exchangeInfo?.comingSoon ? 0.5 : 1 }}
                      >
                        Test
                      </button>
                      <button className="danger" onClick={() => handleDeleteApiKey(provider)}>Remove</button>
                    </div>
                    {apiKeys[provider.toLowerCase()]?.last_test_error && (
                      <div style={{marginTop: '8px', fontSize: '0.75rem', color: 'var(--error)'}}>
                        Last error: {apiKeys[provider.toLowerCase()].last_test_error}
                      </div>
                    )}
                    {apiKeys[provider.toLowerCase()]?.updated_at && (
                      <div style={{marginTop: '4px', fontSize: '0.75rem', color: 'var(--muted)'}}>
                        Updated: {formatDate(apiKeys[provider.toLowerCase()].updated_at)}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
    );
  };

  const renderBots = () => (
      <section className="section active">
        <div className="card">
          <h2 style={{marginBottom: '16px', color: '#ffffff'}}>🤖 Bot Management</h2>
          
          {/* Horizontal Sub-tabs */}
          <div style={{
            display: 'flex', 
            gap: '10px', 
            marginBottom: '24px', 
            marginTop: '16px',
            borderBottom: '2px solid var(--line)', 
            paddingBottom: '10px',
            flexWrap: 'wrap'
          }}>
            <button 
              onClick={() => setBotManagementTab('creation')}
              style={{
                padding: '10px 20px',
                background: botManagementTab === 'creation' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (botManagementTab === 'creation' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: botManagementTab === 'creation' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: botManagementTab === 'creation' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: botManagementTab === 'creation' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🤖 Bot Overview
            </button>
            <button 
              onClick={() => setBotManagementTab('uagents')}
              style={{
                padding: '10px 20px',
                background: botManagementTab === 'uagents' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (botManagementTab === 'uagents' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: botManagementTab === 'uagents' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: botManagementTab === 'uagents' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: botManagementTab === 'uagents' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🤖 uAgents (Fetch.ai)
            </button>
            <button 
              onClick={() => setBotManagementTab('training_quarantine')}
              style={{
                padding: '10px 20px',
                background: botManagementTab === 'training_quarantine' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (botManagementTab === 'training_quarantine' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: botManagementTab === 'training_quarantine' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: botManagementTab === 'training_quarantine' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: botManagementTab === 'training_quarantine' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🎓 Training & Quarantine
            </button>
            <button 
              onClick={() => setBotManagementTab('spawn')}
              style={{
                padding: '10px 20px',
                background: botManagementTab === 'spawn' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (botManagementTab === 'spawn' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: botManagementTab === 'spawn' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: botManagementTab === 'spawn' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: botManagementTab === 'spawn' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              Spawn Bot
            </button>
          </div>
          
          {/* Tab Content */}
          <>
          {botManagementTab === 'creation' && (
          <div className="bot-container">
          <div className="bot-form-card" style={{marginBottom: '20px'}}>
            <h3>Create New Bot</h3>
            <form onSubmit={handleCreateBot}>
              <div className="bot-form-grid">
                <div className="form-group">
                  <label htmlFor="bot-name">Bot Name</label>
                  <input id="bot-name" name="bot-name" placeholder="My Trading Bot" type="text" required />
                </div>
                <div className="form-group">
                  <label htmlFor="bot-budget">Budget (Min R1000)</label>
                  <input 
                    id="bot-budget" 
                    name="bot-budget" 
                    type="number" 
                    min="1000" 
                    step="100"
                    defaultValue="1000"
                    placeholder="1000" 
                    required 
                  />
                  <small style={{color: 'var(--muted)', fontSize: '0.75rem'}}>
                    Minimum R1000 per bot
                  </small>
                </div>
                <div className="form-group">
                  <label htmlFor="bot-exchange">Exchange Platform</label>
                  <select id="bot-exchange" name="bot-exchange" defaultValue="luno">
                    {getAllExchanges().map(exchange => (
                      <option 
                        key={exchange.id} 
                        value={exchange.id}
                        disabled={exchange.comingSoon}
                      >
                        {exchange.icon} {exchange.displayName}
                      </option>
                    ))}
                  </select>
                  <small style={{color: 'var(--muted)', fontSize: '0.75rem', display: 'block', marginTop: '4px'}}>
                    ✅ All 7 exchanges available (Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io)
                  </small>
                </div>
                <div className="form-group">
                  <label htmlFor="bot-risk">Risk Mode</label>
                  <select id="bot-risk" name="bot-risk">
                    <option value="safe">🛡️ Safe</option>
                    <option value="balanced">⚖️ Balanced</option>
                    <option value="aggressive">⚡ Aggressive</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="bot-strategy">Strategy Preset</label>
                  <select id="bot-strategy" name="bot-strategy" defaultValue="adaptive">
                    <option value="adaptive">🧠 Adaptive Core</option>
                    <option value="trend">📈 Trend Follow</option>
                    <option value="mean_reversion">🔄 Mean Reversion</option>
                    <option value="scalping">⚡ Scalping</option>
                  </select>
                </div>
                <div className="form-group">
                  <button type="submit">Create Bot (7 Day Learning)</button>
                </div>
              </div>
              <div style={{marginTop: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--muted)'}}>
                📝 User-created bots undergo 7-day paper trading learning period
              </div>
            </form>
          </div>
          <div className="bot-right" style={{flex: '1 1 100%', maxWidth: '100%'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', gap: '12px', flexWrap: 'wrap'}}>
              <h3 style={{margin: 0}}>Running Bots ({bots.length})</h3>
              <div style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
                <button
                  onClick={handleResumeAllBots}
                  disabled={botControlLoading['all']}
                  style={{
                    padding: '8px 14px',
                    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: botControlLoading['all'] ? 'wait' : 'pointer',
                    opacity: botControlLoading['all'] ? 0.6 : 1
                  }}
                >
                  {botControlLoading['all'] ? '⏳ Resuming...' : '▶️ Resume All Bots'}
                </button>
                <PlatformSelector 
                  value={platformFilter} 
                  onChange={setPlatformFilter}
                  includeAll={true}
                />
              </div>
            </div>
            
            <div className="bot-list">
              {bots.length === 0 ? (
                <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                  No bots.
                </p>
              ) : (
                bots
                  .filter(bot => platformFilter === 'all' || bot.exchange === platformFilter)
                  .map(bot => {
                    const isExpanded = expandedBots[bot.id];
                    const botMode = bot.trading_mode || bot.mode || 'paper';
                    const isLive = botMode === 'live';
                    const paperDays = bot.paper_start_date 
                      ? Math.floor((Date.now() - new Date(bot.paper_start_date).getTime()) / (1000 * 60 * 60 * 24)) + 1
                      : 1;
                    const riskMode = bot.risk_mode || 'safe';
                    const botStatus = getBotStatus(bot);
                    const isActive = botStatus === 'active';
                    const isPaused = ['paused', 'paused_ready'].includes(botStatus);
                    const isQuarantined = botStatus === 'quarantined';
                    const isTraining = ['training', 'training_failed'].includes(botStatus) || bot.training_in_progress;
                    const canStart = ['stopped', 'inactive', 'unknown'].includes(botStatus);
                    const pauseReasonMessage = bot.paused_reason_message || bot.paused_reason;
                    
                    return (
                      <div key={bot.id} className="bot-card" style={{marginBottom: '12px'}}>
                        <div className="bot-header" onClick={() => toggleBotExpand(bot.id)}>
                          <div style={{display: 'flex', alignItems: 'center', gap: '12px', flex: 1}}>
                            <span style={{fontWeight: 600}}>
                              {editingBotId === bot.id ? (
                                <input
                                  type="text"
                                  value={editingBotName}
                                  onChange={(e) => setEditingBotName(e.target.value)}
                                  onClick={(e) => e.stopPropagation()}
                                  onBlur={() => handleSaveBotName(bot.id)}
                                  onKeyPress={(e) => e.key === 'Enter' && handleSaveBotName(bot.id)}
                                  style={{
                                    padding: '4px 8px',
                                    background: 'var(--bg)',
                                    border: '1px solid var(--accent)',
                                    borderRadius: '4px',
                                    color: 'var(--text)',
                                    fontSize: '1rem'
                                  }}
                                  autoFocus
                                />
                              ) : (
                                <>
                                  {bot.name}
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setEditingBotId(bot.id);
                                      setEditingBotName(bot.name);
                                    }}
                                    style={{
                                      marginLeft: '8px',
                                      padding: '2px 6px',
                                      background: 'transparent',
                                      border: '1px solid var(--line)',
                                      borderRadius: '4px',
                                      cursor: 'pointer',
                                      fontSize: '0.75rem'
                                    }}
                                  >
                                    ✏️
                                  </button>
                                </>
                              )}
                            </span>
                            <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                              {bot.exchange ? bot.exchange.toUpperCase() : 'N/A'}
                            </span>
                            {botMode === 'paper' && (
                              <span style={{
                                padding: '2px 8px',
                                background: 'var(--accent)',
                                color: 'white',
                                borderRadius: '12px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                              }}>
                                📄 Day {paperDays}/7
                              </span>
                            )}
                          </div>
                          <div className={`status-dot ${isLive ? 'ok' : 'err'}`} title={isLive ? 'Live Trading' : 'Paper Trading'}></div>
                        </div>
                        
                        {isExpanded && (
                          <div className="bot-details active">
                            {/* Bot Status Information */}
                            <div style={{marginBottom: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px'}}>
                              <div style={{fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px'}}>Bot Status</div>
                              <div style={{display: 'grid', gap: '6px', fontSize: '0.85rem'}}>
                                {isPaused && (
                                  <div>
                                    <strong>Status:</strong> <span style={{color: 'var(--error)'}}>⏸️ PAUSED</span>
                                  </div>
                                )}
                                {pauseReasonMessage && (
                                  <div>
                                    <strong>Pause Reason:</strong> {pauseReasonMessage}
                                  </div>
                                )}
                                {bot.paused_next_action && (
                                  <div>
                                    <strong>Next Action:</strong> {bot.paused_next_action}
                                  </div>
                                )}
                                {bot.quarantine_remaining_seconds !== undefined && bot.quarantine_remaining_seconds !== null && (
                                  <div>
                                    <strong>Release In:</strong> {formatDuration(bot.quarantine_remaining_seconds)}
                                  </div>
                                )}
                                {bot.quarantine_release_at && (
                                  <div>
                                    <strong>Release At:</strong> {formatDate(bot.quarantine_release_at)}
                                  </div>
                                )}
                                {bot.paused_by_system && (
                                  <div>
                                    <span style={{color: 'var(--paper)'}}>⚠️ Paused by System</span>
                                  </div>
                                )}
                                {bot.paused_by_user && (
                                  <div>
                                    <span style={{color: 'var(--muted)'}}>👤 Paused by User</span>
                                  </div>
                                )}
                                {isQuarantined && (
                                  <div>
                                    <span style={{color: 'var(--error)'}}>🔒 In Quarantine</span>
                                  </div>
                                )}
                                {isTraining && (
                                  <div>
                                    <span style={{color: 'var(--accent)'}}>🎓 In Training</span>
                                  </div>
                                )}
                              </div>
                            </div>
                            
                            <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '12px'}}>
                              <div>
                                <label style={{fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                                  Trading Mode
                                </label>
                                <button
                                  onClick={() => handleToggleBotMode(bot.id, botMode)}
                                  style={{
                                    width: '100%',
                                    padding: '8px',
                                    background: isLive ? 'var(--success)' : 'var(--accent)',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '6px',
                                    cursor: 'pointer',
                                    fontWeight: 600
                                  }}
                                >
                                  {botMode.toUpperCase()}
                                </button>
                              </div>
                              
                              <div>
                                <label style={{fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                                  Risk Mode
                                </label>
                                <select
                                  value={riskMode}
                                  onChange={(e) => handleChangeRiskMode(bot.id, e.target.value)}
                                  style={{
                                    width: '100%',
                                    padding: '8px',
                                    background: 'var(--panel)',
                                    border: '1px solid var(--line)',
                                    borderRadius: '6px',
                                    color: 'var(--text)',
                                    cursor: 'pointer'
                                  }}
                                >
                                  <option value="safe">🛡️ Safe</option>
                                  <option value="balanced">⚖️ Balanced</option>
                                  <option value="aggressive">⚡ Aggressive</option>
                                </select>
                              </div>
                            </div>
                            
                            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', marginBottom: '12px'}}>
                              <div style={{textAlign: 'center'}}>
                                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Profit</div>
                                <div style={{fontSize: '1.1rem', fontWeight: 700, color: bot.total_profit > 0 ? 'var(--success)' : 'var(--error)'}}>
                                  R{safeToFixed(bot.total_profit, 2)}
                                </div>
                              </div>
                              <div style={{textAlign: 'center'}}>
                                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Capital</div>
                                <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)'}}>
                                  R{safeToFixed(bot.current_capital, 2)}
                                </div>
                              </div>
                              <div style={{textAlign: 'center'}}>
                                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Trades</div>
                                <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent)'}}>
                                  {bot.trades_count || 0}
                                </div>
                              </div>
                            </div>
                            
                            <div className="buttons" style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px'}}>
                              {isPaused && !isActive && (
                                <button 
                                  onClick={() => handleResumeBot(bot.id)}
                                  disabled={botControlLoading[bot.id]}
                                  style={{
                                    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                                    color: 'white',
                                    border: 'none',
                                    padding: '10px',
                                    borderRadius: '6px',
                                    fontWeight: 600,
                                    cursor: botControlLoading[bot.id] ? 'wait' : 'pointer',
                                    opacity: botControlLoading[bot.id] ? 0.6 : 1
                                  }}
                                >
                                  {botControlLoading[bot.id] ? '⏳ Starting...' : '▶️ Resume Bot'}
                                </button>
                              )}
                              {!isActive && !isPaused && !isQuarantined && !isTraining && canStart && (
                                <button 
                                  onClick={() => handleStartBot(bot.id)}
                                  disabled={botControlLoading[bot.id]}
                                  style={{
                                    background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                                    color: 'white',
                                    border: 'none',
                                    padding: '10px',
                                    borderRadius: '6px',
                                    fontWeight: 600,
                                    cursor: botControlLoading[bot.id] ? 'wait' : 'pointer',
                                    opacity: botControlLoading[bot.id] ? 0.6 : 1
                                  }}
                                >
                                  {botControlLoading[bot.id] ? '⏳ Starting...' : '🚀 Start Bot'}
                                </button>
                              )}
                              <button 
                                className="danger" 
                                onClick={() => handleDeleteBot(bot.id)}
                              >
                                🗑️ Delete Bot
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
              )}
            </div>
          </div>
          </div>
          )}
          {/* uAgents Tab */}
          {botManagementTab === 'uagents' && (
            <div style={{padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
              <h3>🤖 Fetch.ai uAgents</h3>
              <p style={{color: 'var(--muted)', marginBottom: '20px'}}>
                Manage your Fetch.ai uAgents for custom trading strategies
              </p>
              <div className="bot-form-card">
                <h3>🤖 Upload Custom Fetch.ai uAgent</h3>
                <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px'}}>
                  Upload your own Fetch.ai uAgent code (.py file) for custom trading strategies
                </p>
                <form onSubmit={handleCreateUAgent}>
                  <div className="bot-form-grid">
                    <div className="form-group">
                      <label htmlFor="uagent-name">uAgent Name</label>
                      <input id="uagent-name" name="uagent-name" placeholder="My Custom Agent" type="text" required />
                    </div>
                    <div className="form-group">
                      <label htmlFor="uagent-file">Upload uAgent File (.py)</label>
                      <input id="uagent-file" name="uagent-file" type="file" accept=".py" required />
                    </div>
                    <div className="form-group">
                      <label htmlFor="uagent-strategy">Strategy Description</label>
                      <textarea id="uagent-strategy" name="uagent-strategy" placeholder="Describe what this uAgent does..." rows="4"></textarea>
                    </div>
                    <div className="form-group">
                      <button type="submit">Deploy uAgent</button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          )}
          
          {/* Training & Quarantine Unified Tab */}
          {botManagementTab === 'training_quarantine' && (
            <TrainingQuarantineSection />
          )}
          {botManagementTab === 'spawn' && renderSpawnBot()}
          </>
        </div>
      </section>
  );

  const renderSpawnBot = () => (
    <section className="section active">
      <div className="card">
        <h2>Spawn Bot</h2>
        {autoSpawnStatus && (
          <div style={{marginBottom: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '8px', border: '1px solid var(--line)'}}>
            <strong>Autopilot Eligibility (R{safeToFixed(autoSpawnStatus.profit_threshold, 0, '1000')})</strong>
            <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
              Mode: {autoSpawnStatus.trading_mode?.toUpperCase() || 'PAPER'} • Cooldown: {safeNumber(autoSpawnStatus.cooldown_minutes, 0)} min • Max/day: {safeNumber(autoSpawnStatus.max_spawns_per_day, 0)}
            </div>
            <div style={{display: 'grid', gap: '6px', marginTop: '8px'}}>
              {SUPPORTED_PLATFORMS.map(exchange => {
                const profit = safeNumber(autoSpawnStatus.current_profit_per_exchange?.[exchange], 0);
                const eligible = autoSpawnStatus.eligible_per_exchange?.[exchange];
                const reason = autoSpawnStatus.reason_per_exchange?.[exchange] || (eligible ? 'ELIGIBLE' : 'NOT_READY');
                const spawnCount = safeNumber(autoSpawnStatus.spawn_count_today_per_exchange?.[exchange], 0);
                const lastSpawn = autoSpawnStatus.last_spawn_time_per_exchange?.[exchange];
                return (
                  <div key={exchange} style={{padding: '6px 10px', borderRadius: '6px', background: 'var(--panel)'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <span>{getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)}</span>
                      <span style={{fontSize: '0.75rem', color: eligible ? 'var(--success)' : 'var(--muted)'}}>
                        {eligible ? '✅ Eligible' : reason}
                      </span>
                    </div>
                    <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                      Profit: R{safeToFixed(profit, 2)} • Spawns today: {spawnCount} • Last: {lastSpawn ? formatDate(lastSpawn) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {autopilotGrowthStatus && (
          <div style={{marginBottom: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '8px', border: '1px solid var(--line)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <strong>Autopilot Growth Milestones</strong>
              <span style={{fontSize: '0.75rem', color: autopilotGrowthStatus?.enabled ? 'var(--success)' : 'var(--muted)'}}>
                Growth Mode: {autopilotGrowthStatus?.enabled ? 'ON' : 'OFF'}
              </span>
            </div>
            <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
              Milestone size: R{safeToFixed(autopilotGrowthStatus.profit_threshold_zar, 0, '1000')} • Milestones tracked per platform
            </div>
            <div style={{display: 'grid', gap: '6px', marginTop: '8px'}}>
              {SUPPORTED_PLATFORMS.map(exchange => {
                const status = autopilotGrowthStatus.platforms?.[exchange] || {};
                const blocked = status.blocked_reasons?.length ? status.blocked_reasons.join(', ') : (status.eligible ? 'ELIGIBLE' : 'NOT_READY');
                return (
                  <div key={`growth-${exchange}`} style={{padding: '6px 10px', borderRadius: '6px', background: 'var(--panel)'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <span>{getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)}</span>
                      <span style={{fontSize: '0.75rem', color: status.eligible ? 'var(--success)' : 'var(--muted)'}}>
                        {status.eligible ? '✅ Eligible' : blocked}
                      </span>
                    </div>
                    <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                      Profit: R{safeToFixed(status.realized_profit_zar, 2)} • Next bot at: R{safeToFixed(status.next_threshold_zar, 0)} • Bots spawned: {safeNumber(status.milestones_spawned, 0)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {autopilotReinvestStatus && (
          <div style={{marginBottom: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '8px', border: '1px solid var(--line)'}}>
            <strong>Daily Reinvest Status</strong>
            <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
              Minimum reinvest: R{safeToFixed(autopilotReinvestStatus.min_reinvest_zar, 0, '100')}
            </div>
            <div style={{display: 'grid', gap: '6px', marginTop: '8px'}}>
              {SUPPORTED_PLATFORMS.map(exchange => {
                const status = autopilotReinvestStatus.platforms?.[exchange] || {};
                const blocked = status.blocked_reasons?.length ? status.blocked_reasons.join(', ') : (status.eligible ? 'ELIGIBLE' : 'NOT_READY');
                return (
                  <div key={`reinvest-${exchange}`} style={{padding: '6px 10px', borderRadius: '6px', background: 'var(--panel)'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <span>{getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)}</span>
                      <span style={{fontSize: '0.75rem', color: status.eligible ? 'var(--success)' : 'var(--muted)'}}>
                        {status.eligible ? '✅ Eligible' : blocked}
                      </span>
                    </div>
                    <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                      Last Reinvest: {status.last_reinvest_date || '—'} • Amount: R{safeToFixed(status.last_reinvest_amount, 2, '0.00')} • Next run: {status.next_run ? formatDate(status.next_run) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <div className="bot-form-card">
          <h3>Autonomous Spawning</h3>
          <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: 0}}>
            Bot creation is fully automated. Autopilot will spawn new bots when eligibility,
            risk guardrails, and exchange caps allow. Manual spawning is disabled.
          </p>
        </div>
      </div>
    </section>
  );

  const renderProfile = () => {
    
    return (
      <section className="section active">
        <div className="card">
          <h2 style={{color: '#ffffff'}}>Profile Settings</h2>
          <div className="profile-grid">
            <div className="field-group">
              <label>Full Name</label>
              <input 
                type="text" 
                value={profileData.first_name || ''} 
                onChange={(e) => handleProfileChange('first_name', e.target.value)}
              />
            </div>
            <div className="field-group">
              <label>Email Address</label>
              <input 
                type="email" 
                value={profileData.email || ''} 
                onChange={(e) => handleProfileChange('email', e.target.value)}
              />
            </div>
            <div className="field-group">
              <label>Display Currency</label>
              <select 
                value={profileData.currency || 'ZAR'} 
                onChange={(e) => handleProfileChange('currency', e.target.value)}
              >
                <option value="ZAR">ZAR (South African Rand)</option>
                <option value="USD">USD (US Dollar)</option>
                <option value="EUR">EUR (Euro)</option>
                <option value="GBP">GBP (British Pound)</option>
              </select>
            </div>
            <div className="field-group">
              <label>New Password (optional)</label>
              <input 
                type="password" 
                placeholder="Leave blank to keep current" 
                value={profileData.new_password || ''}
                onChange={(e) => handleProfileChange('new_password', e.target.value)}
              />
            </div>
            <div className="field-group">
              <label>&nbsp;</label>
              <button onClick={handleProfileSave}>Save Profile</button>
            </div>
          </div>
          
          <div style={{marginTop: '24px', padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
            <h3 style={{marginBottom: '12px'}}>Account Information</h3>
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
              <div>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Account Status</div>
                <div style={{fontWeight: 600, marginTop: '4px', color: 'var(--success)'}}>Active</div>
              </div>
              <div>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Member Since</div>
                <div style={{fontWeight: 600, marginTop: '4px'}}>{formatDate(user?.created_at, { format: 'localeDateString' })}</div>
              </div>
              <div>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total Bots</div>
                <div style={{fontWeight: 600, marginTop: '4px'}}>{bots.length}</div>
              </div>
              <div>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Active Bots</div>
                <div style={{fontWeight: 600, marginTop: '4px', color: 'var(--success)'}}>
                  {(() => {
                    const activeBots = bots.filter(b => b.status === 'active');
                    const paperBots = activeBots.filter(b => b.trading_mode === 'paper').length;
                    const liveBots = activeBots.filter(b => b.trading_mode === 'live').length;
                    if (liveBots > 0) {
                      return `${activeBots.length} (${liveBots} live, ${paperBots} paper)`;
                    }
                    return `${activeBots.length} (paper)`;
                  })()}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  };

  // Handle Start Fresh - Wipe paper data
  const handleStartFresh = async () => {
    const confirmPhrase = window.prompt(
      'WARNING: This will delete all paper trading data!\n\n' +
      'This includes:\n' +
      '- All paper trading bots\n' +
      '- All paper trades history\n' +
      '- Bot telemetry data\n' +
      '- Risk lock states\n\n' +
      'Type "DELETE_ALL_PAPER_DATA" to confirm:'
    );

    if (confirmPhrase !== 'DELETE_ALL_PAPER_DATA') {
      if (confirmPhrase !== null) {
        showNotification('Incorrect confirmation phrase', 'error');
      }
      return;
    }

    try {
      const response = await axios.post(
        `${API}/admin/start-fresh`,
        {
          confirm_phrase: 'DELETE_ALL_PAPER_DATA',
          scope: 'paper_only',
          also_reset_risk_locks: true
        },
        axiosConfig
      );

      if (response.data.success) {
        const summary = response.data.summary;
        showNotification(
          `Start Fresh completed! Deleted: ${summary.bots_deleted} bots, ${summary.trades_deleted} trades`,
          'success'
        );
        
        // Refresh data
        loadBots();
        loadSystemStats();
        loadAdminUsers();
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Unknown error';
      showNotification(`Start Fresh failed: ${errorMsg}`, 'error');
      console.error('Start Fresh error:', err);
    }
  };

  // Handle API Key Migration
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

  const renderAdmin = () => {
    
    return (
      <section className="section active">
        <div className="card">
          <h2 style={{color: '#ffffff'}}>🔧 Admin Panel (God Mode)</h2>
          <div style={{display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px', marginBottom: '24px'}}>
            <div style={{
              padding: '6px 12px',
              borderRadius: '6px',
              background: adminApiHealth.status === 'Error'
                ? 'var(--error)'
                : adminApiHealth.status === 'Unknown'
                  ? 'var(--line)'
                  : 'var(--success)',
              color: 'white',
              fontSize: '0.8rem',
              fontWeight: 600
            }}>
              Admin API: {adminApiHealth.status}
            </div>
            <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
              Last check: {adminApiHealth.lastCheck ? formatDate(adminApiHealth.lastCheck) : '—'}
            </div>
            {adminApiHealth.error && (
              <div style={{fontSize: '0.75rem', color: 'var(--error)'}}>
                {adminApiHealth.error}
              </div>
            )}
          </div>
          
          {/* VPS Resource Summary */}
          {systemStats?.vps_resources && (
            <div style={{marginBottom: '24px'}}>
              <h3 style={{marginBottom: '12px', color: '#ffffff'}}>🖥️ VPS Resources</h3>
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>CPU Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.cpu.usage_percent, 0) > 80 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.cpu.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.cpu.count, 0)} cores
                    {systemStats.vps_resources.cpu.load_average && 
                      ` • Load: ${systemStats.vps_resources.cpu.load_average['1min']}`
                    }
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>RAM Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.memory.usage_percent, 0) > 85 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.memory.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.memory.used_gb, 0)} / {safeNumber(systemStats.vps_resources.memory.total_gb, 0)} GB used
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>Disk Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.disk.usage_percent, 0) > 85 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.disk.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.disk.free_gb, 0)} GB free
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* System Stats */}
          {systemStats && (
            <div style={{marginBottom: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px'}}>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.users?.total, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Users</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.bots?.active, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Active Bots</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.trades?.total, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Trades</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>R{safeToFixed(systemStats.profit?.total, 2)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Profit</div>
              </div>
            </div>
          )}

          {systemStats && (
            <div style={{marginBottom: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginBottom: '8px'}}>System Modes</div>
                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                  Paper: {safeNumber(systemStats.system_modes?.paper_trading, 0)} • Live: {safeNumber(systemStats.system_modes?.live_trading, 0)} • Autopilot: {safeNumber(systemStats.system_modes?.autopilot, 0)}
                </div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginBottom: '8px'}}>Scheduler Status</div>
                <div style={{fontSize: '0.75rem', color: systemStats.scheduler_status?.running ? 'var(--success)' : 'var(--error)'}}>
                  {systemStats.scheduler_status?.running ? 'Running' : 'Stopped'}
                </div>
              </div>
            </div>
          )}

          {systemStats?.exchange_breakdown && (
            <div style={{marginBottom: '24px', padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
              <h3 style={{margin: 0, color: '#ffffff'}}>📊 Exchange Breakdown</h3>
              <div style={{marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
                {SUPPORTED_PLATFORMS.map(exchange => {
                  const breakdown = systemStats.exchange_breakdown?.[exchange] || {};
                  return (
                    <div key={exchange} style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px'}}>
                      <div style={{fontWeight: 600, marginBottom: '6px'}}>{getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Bots: {safeNumber(breakdown.bots, 0)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Trades: {safeNumber(breakdown.trades, 0)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Profit: R{safeToFixed(breakdown.profit, 2)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          
          {/* Per-User Storage Usage */}
          {storageError && (
            <div style={{marginBottom: '24px', padding: '12px 16px', borderRadius: '8px', border: '1px solid var(--error)', background: 'rgba(239, 68, 68, 0.1)', color: 'var(--error)'}}>
              ⚠️ Unable to load storage data: {storageError}
            </div>
          )}
          {storageData && (
            <div style={{marginBottom: '24px', padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px'}}>
                <h3 style={{margin: 0, color: '#ffffff'}}>💾 User Storage Usage</h3>
                <div style={{fontSize: '0.9rem', color: '#cccccc'}}>
                  Total: {storageTotals ? safeToFixed(storageTotals.totalMb, 2) : '0.00'} MB ({storageTotals ? safeToFixed(storageTotals.totalGb, 2) : '0.00'} GB)
                </div>
              </div>
              <div style={{maxHeight: '200px', overflowY: 'auto'}}>
                {storageData.users && storageData.users.length > 0 ? (
                  storageData.users.map((userStorage) => {
                    const storageMb = userStorage.total_storage_mb ?? userStorage.storage_mb ?? 0;
                    return (
                      <div key={userStorage.user_id} style={{
                        padding: '8px 12px',
                        marginBottom: '6px',
                        background: 'var(--glass)',
                        borderRadius: '4px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <div style={{flex: 1}}>
                        <div style={{fontWeight: 600, fontSize: '0.9rem', color: '#ffffff'}}>{userStorage.name || 'Unknown'}</div>
                          <div style={{fontSize: '0.75rem', color: '#cccccc'}}>{userStorage.email}</div>
                        </div>
                        <div style={{fontWeight: 700, fontSize: '0.95rem', color: storageMb > 100 ? 'var(--error)' : 'var(--success)'}}>
                          {safeToFixed(storageMb, 2)} MB
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div style={{textAlign: 'center', padding: '20px', color: '#cccccc'}}>
                    No storage data available
                  </div>
                )}
              </div>
            </div>
          )}
          
          {/* Users Table */}
          <div style={{overflowX: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
              <thead>
                <tr style={{borderBottom: '2px solid var(--line)'}}>
                  <th style={{padding: '12px', textAlign: 'left', color: '#ffffff', fontWeight: 600}}>User</th>
                  <th style={{padding: '12px', textAlign: 'left', color: '#ffffff', fontWeight: 600}}>Email</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Bots</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Status</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {allUsers.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{padding: '40px', textAlign: 'center', color: '#cccccc'}}>
                      No users found
                    </td>
                  </tr>
                ) : (
                  allUsers.map(usr => (
                    <tr key={usr.id} style={{borderBottom: '1px solid var(--line)'}}>
                      <td style={{padding: '12px', color: '#ffffff'}}>{usr.first_name || 'N/A'}</td>
                      <td style={{padding: '12px', color: '#ffffff'}}>{usr.email}</td>
                      <td style={{padding: '12px', textAlign: 'center', color: '#ffffff'}}>
                        {usr.stats?.total_bots || 0}
                      </td>
                      <td style={{padding: '12px', textAlign: 'center'}}>
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: usr.status === 'blocked' ? 'var(--error)' : 'var(--success)',
                          color: 'white'
                        }}>
                          {usr.status === 'blocked' ? 'Blocked' : 'Active'}
                        </span>
                      </td>
                      <td style={{padding: '12px', textAlign: 'center'}}>
                        <div style={{display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'wrap'}}>
                          <button 
                            onClick={() => handleChangePassword(usr.id)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: 'var(--accent2)',
                              color: 'var(--text)',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            Change PW
                          </button>
                          <button 
                            onClick={() => handleBlockUser(usr.id, usr.status === 'blocked')}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: usr.status === 'blocked' ? 'var(--success)' : '#f59e0b',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            {usr.status === 'blocked' ? 'Unblock' : 'Block'}
                          </button>
                          <button 
                            onClick={() => handleDeleteUser(usr.id)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: 'var(--error)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          
          {/* AI Bodyguard Status */}
          {bodyguardStatus && (
            <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '2px solid ' + (bodyguardStatus.health_score >= 80 ? 'var(--success)' : bodyguardStatus.health_score >= 60 ? '#f59e0b' : 'var(--error)')}}>
              <h3 style={{marginBottom: '16px', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '8px'}}>
                🛡️ AI Bodyguard Status
                <span style={{
                  fontSize: '0.75rem', 
                  padding: '4px 8px', 
                  borderRadius: '4px', 
                  background: bodyguardStatus.health_score >= 80 ? 'var(--success)' : bodyguardStatus.health_score >= 60 ? '#f59e0b' : 'var(--error)',
                  color: 'white'
                }}>
                  {bodyguardStatus.health_status}
                </span>
              </h3>
              
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: bodyguardStatus.health_score >= 80 ? 'var(--success)' : 'var(--error)'}}>{bodyguardStatus.health_score}</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Health Score</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--text)'}}>{bodyguardStatus.system_health?.cpu_usage}%</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>CPU</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--text)'}}>{bodyguardStatus.system_health?.memory_usage}%</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Memory</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent)'}}>{bodyguardStatus.trading_health?.active_bots}</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Active Bots</div>
                </div>
              </div>
              
              {(bodyguardStatus.issues?.length > 0 || bodyguardStatus.warnings?.length > 0) && (
                <div style={{marginTop: '16px'}}>
                  {bodyguardStatus.issues?.length > 0 && (
                    <div style={{marginBottom: '12px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '6px', border: '1px solid var(--error)'}}>
                      <div style={{fontWeight: 600, color: 'var(--error)', marginBottom: '8px'}}>🚨 Critical Issues ({bodyguardStatus.issues.length})</div>
                      <ul style={{margin: 0, paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text)'}}>
                        {bodyguardStatus.issues.map((issue, idx) => (
                          <li key={idx} style={{marginBottom: '4px'}}>{issue}</li>
          ))}
                      </ul>
                    </div>
                  )}
                  
                  {bodyguardStatus.warnings?.length > 0 && (
                    <div style={{padding: '12px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '6px', border: '1px solid #f59e0b'}}>
                      <div style={{fontWeight: 600, color: '#f59e0b', marginBottom: '8px'}}>⚠️ Warnings ({bodyguardStatus.warnings.length})</div>
                      <ul style={{margin: 0, paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text)'}}>
                        {bodyguardStatus.warnings.map((warning, idx) => (
                          <li key={idx} style={{marginBottom: '4px'}}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              
              <div style={{marginTop: '12px', fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'right'}}>
                Last check: {formatDate(bodyguardStatus.timestamp)}
              </div>
            </div>
          )}
          
          {/* User Storage Tracking */}
          {storageData && (
            <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
              <h3 style={{marginBottom: '16px', color: 'var(--accent)'}}>💾 User Storage Tracking</h3>
              
              <div style={{marginBottom: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total System Storage</div>
                  <div style={{fontSize: '1.5rem', fontWeight: 700, color: 'var(--text)'}}>{storageTotals ? safeToFixed(storageTotals.totalMb, 2) : '0.00'} MB</div>
                </div>
                <div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total Users</div>
                  <div style={{fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent)'}}>{storageTotals ? safeNumber(storageTotals.totalUsers, 0) : 0}</div>
                </div>
              </div>
              
              <div style={{maxHeight: '400px', overflowY: 'auto'}}>
                <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
                  <thead style={{position: 'sticky', top: 0, background: 'var(--panel)'}}>
                    <tr style={{borderBottom: '2px solid var(--line)'}}>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>User</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Chats</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Trades</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Bots</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {storageData.users?.map((usr, idx) => (
                      <tr key={idx} style={{borderBottom: '1px solid var(--line)'}}>
                        <td style={{padding: '12px'}}>
                          <div>{usr.name || 'Unknown'}</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.email}</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.chat_messages?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.chat_messages?.count} msgs</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.trades?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.trades?.count} trades</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.bots?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.bots?.count} bots</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '6px 12px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            background: usr.total_storage_mb > 10 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                            color: usr.total_storage_mb > 10 ? '#f59e0b' : 'var(--success)'
                          }}>
                            {safeToFixed(usr.total_storage_mb, 2)} MB
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          
          {/* User Management Table - Interactive */}
          <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
              <h3 style={{margin: 0, color: 'var(--accent)', fontWeight: 'bold'}}>👥 User Management</h3>
              <button
                onClick={loadAdminUsers}
                disabled={loadingUsers}
                style={{
                  padding: '8px 16px',
                  fontSize: '0.85rem',
                  background: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: loadingUsers ? 'not-allowed' : 'pointer',
                  opacity: loadingUsers ? 0.6 : 1,
                  fontWeight: 600
                }}
              >
                {loadingUsers ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
            </div>
            
            {loadingUsers ? (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)'}}>
                Loading users...
              </div>
            ) : adminUsers.length === 0 ? (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)'}}>
                No users found
              </div>
            ) : (
              <div style={{overflowX: 'auto'}}>
                <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
                  <thead>
                    <tr style={{borderBottom: '2px solid var(--line)'}}>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>Username</th>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>Email</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Role</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Status</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>API Keys</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Bots</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.map(usr => (
                      <tr key={usr.id} style={{borderBottom: '1px solid var(--line)'}}>
                        <td style={{padding: '12px'}}>{usr.first_name || 'N/A'}</td>
                        <td style={{padding: '12px'}}>{usr.email}</td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: usr.role === 'admin' ? '#8b5cf6' : 'var(--glass)',
                            color: usr.role === 'admin' ? 'white' : 'var(--text)'
                          }}>
                            {usr.role || 'user'}
                          </span>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: usr.status === 'blocked' ? 'var(--error)' : 'var(--success)',
                            color: 'white'
                          }}>
                            {usr.status === 'blocked' ? '🚫 Blocked' : '✓ Active'}
                          </span>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          {usr.api_keys_count > 0 ? `✓ ${usr.api_keys_count}` : '—'}
                        </td>
                        <td style={{padding: '12px', textAlign: 'center', fontWeight: 600}}>
                          {usr.bots_count || 0}
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'wrap'}}>
                            <button
                              onClick={() => handleResetPassword(usr.id)}
                              disabled={actionLoading[`reset-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`reset-${usr.id}`] ? '#666' : '#3b82f6',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`reset-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`reset-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`reset-${usr.id}`] ? '...' : '🔑 Reset PW'}
                            </button>
                            <button
                              onClick={() => handleToggleBlockUser(usr.id, usr.status)}
                              disabled={actionLoading[`block-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`block-${usr.id}`] ? '#666' : (usr.status === 'blocked' ? 'var(--success)' : '#f59e0b'),
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`block-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`block-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`block-${usr.id}`] ? '...' : (usr.status === 'blocked' ? '✓ Unblock' : '🚫 Block')}
                            </button>
                            <button
                              onClick={() => handleDeleteUserAdmin(usr.id)}
                              disabled={actionLoading[`delete-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`delete-${usr.id}`] ? '#666' : 'var(--error)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`delete-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`delete-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`delete-${usr.id}`] ? '...' : '🗑️ Delete'}
                            </button>
                            <button
                              onClick={() => handleForceLogout(usr.id)}
                              disabled={actionLoading[`logout-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`logout-${usr.id}`] ? '#666' : '#ef4444',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`logout-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`logout-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`logout-${usr.id}`] ? '...' : '🚪 Logout'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          
          {/* Bot Override Panel - Interactive */}
          <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
              <h3 style={{margin: 0, color: 'var(--accent)', fontWeight: 'bold'}}>🤖 Bot Control Panel</h3>
              <button
                onClick={loadAdminBots}
                disabled={loadingBots}
                style={{
                  padding: '8px 16px',
                  fontSize: '0.85rem',
                  background: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: loadingBots ? 'not-allowed' : 'pointer',
                  opacity: loadingBots ? 0.6 : 1,
                  fontWeight: 600
                }}
              >
                {loadingBots ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
            </div>
            
            {/* User and Bot Selection */}
            <div style={{marginBottom: '20px', padding: '16px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--accent)'}}>
              <h4 style={{margin: '0 0 12px 0', color: 'var(--accent)', fontSize: '0.9rem', fontWeight: 'bold'}}>🎯 Select Target</h4>
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '12px'}}>
                {/* User Selection */}
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--text)', marginBottom: '6px', fontWeight: 600}}>
                    Select User
                  </label>
                  <select
                    value={selectedUserId}
                    onChange={(e) => handleUserSelection(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.85rem',
                      background: 'var(--panel)',
                      color: 'var(--text)',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    <option value="">-- Select a User --</option>
                    {adminUsers.map(usr => (
                      <option key={usr.id} value={usr.id}>
                        {usr.name || usr.first_name || usr.email} ({usr.email})
                      </option>
                    ))}
                  </select>
                </div>
                
                {/* Bot Selection */}
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--text)', marginBottom: '6px', fontWeight: 600}}>
                    Select Bot
                  </label>
                  <select
                    value={selectedBotId}
                    onChange={(e) => setSelectedBotId(e.target.value)}
                    disabled={!selectedUserId}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.85rem',
                      background: selectedUserId ? 'var(--panel)' : '#e0e0e0',
                      color: selectedUserId ? 'var(--text)' : '#999',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: selectedUserId ? 'pointer' : 'not-allowed',
                      fontWeight: 600
                    }}
                  >
                    <option value="">-- Select a Bot --</option>
                    {filteredAdminBots.map(bot => (
                      <option key={bot.bot_id} value={bot.bot_id}>
                        {bot.name} ({bot.exchange?.toUpperCase()}) - {bot.mode === 'live' ? '💰 Live' : '📝 Paper'}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              
              {selectedUserId && filteredAdminBots.length === 0 && (
                <div style={{marginTop: '12px', padding: '8px 12px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '4px', fontSize: '0.8rem', color: '#f59e0b'}}>
                  ⚠️ Selected user has no bots
                </div>
              )}
            </div>
            
            {/* Bot Actions - Only visible when bot is selected */}
            {selectedBotId && (() => {
              const selectedBot = filteredAdminBots.find(b => b.bot_id === selectedBotId);
              if (!selectedBot) return null;
              
              return (
                <div style={{padding: '16px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--success)'}}>
                  <h4 style={{margin: '0 0 12px 0', color: 'var(--success)', fontSize: '0.9rem'}}>⚙️ Bot Actions</h4>
                  
                  {/* Bot Info */}
                  <div style={{marginBottom: '16px', padding: '12px', background: 'var(--panel)', borderRadius: '4px'}}>
                    <div style={{fontWeight: 700, fontSize: '1rem', marginBottom: '4px'}}>{selectedBot.name}</div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>
                      User: {selectedBot.username} • Exchange: {selectedBot.exchange?.toUpperCase()} • 
                      Status: {selectedBot.status === 'active' ? '▶ Active' : selectedBot.status === 'paused' ? '⏸ Paused' : '⏹ Stopped'}
                    </div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginTop: '4px'}}>
                      Mode: {selectedBot.mode === 'live' ? '💰 Live Trading' : '📝 Paper Trading'} • 
                      Capital: R{safeToFixed(selectedBot.current_capital, 2)} • 
                      P/L: R{safeToFixed(selectedBot.profit_loss, 2)}
                    </div>
                  </div>
                  
                  {/* Action Buttons */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px'}}>
                    {/* Pause/Resume */}
                    <button
                      onClick={() => handleToggleBotPause(selectedBot.bot_id, selectedBot.status)}
                      disabled={actionLoading[`pause-${selectedBot.bot_id}`]}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: actionLoading[`pause-${selectedBot.bot_id}`] ? '#666' : (selectedBot.status === 'active' ? '#f59e0b' : 'var(--success)'),
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: actionLoading[`pause-${selectedBot.bot_id}`] ? 'not-allowed' : 'pointer',
                        opacity: actionLoading[`pause-${selectedBot.bot_id}`] ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {actionLoading[`pause-${selectedBot.bot_id}`] ? '...' : (selectedBot.status === 'active' ? '⏸ Pause Bot' : '▶ Resume Bot')}
                    </button>
                    
                    {/* Change Mode: Paper */}
                    <button
                      onClick={() => handleChangeBotMode(selectedBot.bot_id, 'paper')}
                      disabled={actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper'}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: selectedBot.mode === 'paper' ? 'var(--success)' : (actionLoading[`mode-${selectedBot.bot_id}`] ? '#666' : 'var(--glass)'),
                        color: selectedBot.mode === 'paper' ? 'white' : 'var(--text)',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        cursor: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper') ? 'not-allowed' : 'pointer',
                        opacity: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper') ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {selectedBot.mode === 'paper' ? '✓ Paper Mode' : '📝 Set Paper'}
                    </button>
                    
                    {/* Change Mode: Live */}
                    <button
                      onClick={() => handleChangeBotMode(selectedBot.bot_id, 'live')}
                      disabled={actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live'}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: selectedBot.mode === 'live' ? '#f59e0b' : (actionLoading[`mode-${selectedBot.bot_id}`] ? '#666' : 'var(--glass)'),
                        color: selectedBot.mode === 'live' ? 'white' : 'var(--text)',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        cursor: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live') ? 'not-allowed' : 'pointer',
                        opacity: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live') ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {selectedBot.mode === 'live' ? '✓ Live Mode' : '💰 Set Live'}
                    </button>
                    
                    {/* Change Exchange */}
                    <div>
                      <select
                        value={selectedBot.exchange}
                        onChange={(e) => handleChangeBotExchange(selectedBot.bot_id, e.target.value)}
                        disabled={actionLoading[`exchange-${selectedBot.bot_id}`]}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          fontSize: '0.85rem',
                          background: 'var(--glass)',
                          color: 'var(--text)',
                          border: '1px solid var(--line)',
                          borderRadius: '4px',
                          cursor: actionLoading[`exchange-${selectedBot.bot_id}`] ? 'not-allowed' : 'pointer',
                          opacity: actionLoading[`exchange-${selectedBot.bot_id}`] ? 0.6 : 1,
                          fontWeight: 600
                        }}
                      >
                        <option value="binance">Binance</option>
                        <option value="luno">Luno</option>
                        <option value="kucoin">KuCoin</option>
                        <option value="bybit">Bybit</option>
                        <option value="kraken">Kraken</option>
                        <option value="bitget">Bitget</option>
                        <option value="gate">Gate.io</option>
                      </select>
                    </div>
                  </div>
                  
                  <div style={{marginTop: '12px', padding: '10px', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '4px', fontSize: '0.75rem', color: 'var(--muted)'}}>
                    ℹ️ All admin actions are logged in the audit trail. Actions apply ONLY to the selected bot.
                  </div>
                </div>
              );
            })()}
            
            {!selectedBotId && (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)', fontSize: '0.9rem'}}>
                👆 Select a user and bot above to perform admin actions
              </div>
            )}
          </div>
          
          {/* Admin Tools - All in One Section */}
          <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--accent)'}}>
            <h3 style={{marginBottom: '16px', color: 'var(--accent)'}}>🛠️ System Administration</h3>
            
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
              <button 
                onClick={handleTriggerBodyguard}
                disabled={aiTaskLoading === 'bodyguard'}
                style={{
                  padding: '12px 16px',
                  background: aiTaskLoading === 'bodyguard' ? '#666' : 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: aiTaskLoading === 'bodyguard' ? 'wait' : 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s',
                  opacity: aiTaskLoading === 'bodyguard' ? 0.7 : 1
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                {aiTaskLoading === 'bodyguard' ? '⏳ Scanning...' : '🛡️ AI Bodyguard'}
              </button>
              
              <button 
                onClick={handleEmailAllUsers}
                style={{
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                📧 Email All Users
              </button>
              
              <button 
                onClick={async () => {
                  try {
                    const res = await axios.get(`${API}/admin/health-check`, axiosConfig);
                    const services = res.data.services;
                    const score = res.data.health_score;
                    
                    let statusHTML = `Health Score: ${score}/100\n\n`;
                    statusHTML += 'Services Status:\n';
                    Object.entries(services).forEach(([name, status]) => {
                      const emoji = status === 'healthy' ? '✅' : '❌';
                      statusHTML += `${emoji} ${name}: ${status}\n`;
                    });
                    
                    // Add health report to chat
                    const reportMsg = `System Health Report (${score}/100)\n\n${statusHTML}`;
                    setChatMessages(prev => [...prev, 
                      { role: 'user', content: 'Check system health' },
                      { role: 'assistant', content: reportMsg }
                    ]);
                    
                    // Redirect to chat section
                    setActiveSection('welcome');
                    setTimeout(() => showSection('welcome'), 100);
                    
                    showNotification(`System Health: ${score}/100 - Check chat for details`, score >= 80 ? 'success' : 'warning');
                  } catch (err) {
                    showNotification('Health check failed', 'error');
                  }
                }}
                style={{
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                🏥 System Health
              </button>
            </div>
            
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '12px', lineHeight: '1.5'}}>
              Monitor system health, send notifications, and check backend services in real-time
            </p>
          </div>
          
          {/* Danger Zone - Admin Only Destructive Actions */}
          <div style={{
            marginTop: '24px', 
            padding: '20px', 
            background: 'rgba(239, 68, 68, 0.1)', 
            borderRadius: '8px', 
            border: '2px solid var(--error)'
          }}>
            <h3 style={{marginBottom: '16px', color: 'var(--error)', display: 'flex', alignItems: 'center', gap: '8px'}}>
              ⚠️ Danger Zone
              <span style={{fontSize: '0.75rem', fontWeight: 'normal', color: 'var(--muted)'}}>
                (Admin Only - Destructive Actions)
              </span>
            </h3>
            
            <div style={{display: 'grid', gap: '12px'}}>
              {/* Start Fresh Button */}
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                borderRadius: '6px',
                border: '1px solid var(--error)'
              }}>
                <div style={{marginBottom: '12px'}}>
                  <h4 style={{margin: '0 0 8px 0', color: 'var(--text)', fontSize: '1rem'}}>
                    🗑️ Start Fresh (Wipe Paper Data)
                  </h4>
                  <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: 0, lineHeight: '1.5'}}>
                    Delete all paper trading bots, trades, and telemetry. Resets risk locks. 
                    <strong style={{color: 'var(--error)'}}>Cannot be undone!</strong>
                  </p>
                </div>
                <button
                  onClick={handleStartFresh}
                  style={{
                    padding: '10px 20px',
                    background: 'var(--error)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                    width: '100%'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  🗑️ Start Fresh (Delete Paper Data)
                </button>
              </div>

              {/* API Key Migration Button */}
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                borderRadius: '6px',
                border: '1px solid #f59e0b'
              }}>
                <div style={{marginBottom: '12px'}}>
                  <h4 style={{margin: '0 0 8px 0', color: 'var(--text)', fontSize: '1rem'}}>
                    🔐 Migrate API Key Encryption
                  </h4>
                  <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: 0, lineHeight: '1.5'}}>
                    Migrate API keys from JWT_SECRET-derived encryption to dedicated AMARKTAI_FERNET_KEY.
                    Required when upgrading encryption method.
                  </p>
                </div>
                <button
                  onClick={handleMigrateApiKeys}
                  style={{
                    padding: '10px 20px',
                    background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                    width: '100%'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  🔐 Migrate API Keys
                </button>
              </div>
            </div>
            
            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'rgba(239, 68, 68, 0.1)',
              borderRadius: '4px',
              fontSize: '0.75rem',
              color: 'var(--error)',
              lineHeight: '1.5'
            }}>
              <strong>⚠️ Warning:</strong> These actions are irreversible and will affect system data.
              All actions are logged in the audit trail. Use with extreme caution.
            </div>
          </div>
          
          <div style={{marginTop: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--error)', fontSize: '0.85rem'}}>
            <p style={{color: 'var(--error)', fontWeight: 600, marginBottom: '8px'}}>⚠️ Admin Warning</p>
            <p style={{color: 'var(--muted)'}}>
              You have full control over all users. Use these powers responsibly. All actions are logged.
            </p>
          </div>
        </div>
      </section>
    );
  };

  const renderSystemMode = () => (
    <section className="section active">
      <div className="card">
        <h2 style={{color: '#ffffff'}}>System Mode</h2>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px'}}>
          <div className="system-card" onClick={() => toggleSystemMode('paperTrading')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.paperTrading ? 'var(--success)' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>🧪 Paper Trading</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>Practice with simulated funds</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.paperTrading ? 'var(--success)' : 'var(--error)'}}>
              {systemModes.paperTrading ? '✓ ON' : '✗ OFF'}
            </div>
          </div>
          <div className="system-card" onClick={() => toggleSystemMode('liveTrading')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.liveTrading ? '#f59e0b' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>💰 Live Trading</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>⚠️ Execute REAL trades</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.liveTrading ? '#f59e0b' : 'var(--error)'}}>
              {systemModes.liveTrading ? '⚡ ON' : '✗ OFF'}
            </div>
          </div>
          <div className="system-card" onClick={() => toggleSystemMode('autopilot')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.autopilot ? 'var(--success)' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>🤖 Autopilot</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>Autonomous 24/7 trading</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.autopilot ? 'var(--success)' : 'var(--error)'}}>
              {systemModes.autopilot ? '✓ ON' : '✗ OFF'}
            </div>
          </div>
        </div>
        <div style={{marginTop: '12px', padding: '16px', background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: '8px'}}>
          <div style={{fontWeight: 700, marginBottom: '8px', color: 'var(--text)'}}>🛡️ Risk Profile</div>
          <select
            value={riskProfile}
            onChange={(e) => handleRiskProfileChange(e.target.value)}
            style={{
              width: '100%',
              padding: '10px',
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              borderRadius: '6px',
              color: 'var(--text)',
              cursor: 'pointer',
              maxWidth: '320px'
            }}
          >
            <option value="safe">Safe (15% daily loss/drawdown)</option>
            <option value="balanced">Balanced (20% daily loss/drawdown)</option>
            <option value="risky">Risky (25% daily loss/drawdown)</option>
          </select>
          <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginTop: '8px'}}>
            Bodyguard uses this tier to pause bots when drawdown exceeds your selected threshold.
          </div>
        </div>
        <div style={{marginTop: '24px', padding: '16px', background: 'var(--panel)', border: '2px solid var(--error)', borderRadius: '8px'}}>
          <h3 style={{color: 'var(--error)', marginBottom: '8px'}}>🚨 Emergency Controls</h3>
          <p style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '12px'}}>
            Immediately stop ALL bots and trading activity system-wide
          </p>
          <button 
            onClick={handleEmergencyStop}
            style={{
              padding: '12px 24px', 
              background: 'var(--error)', 
              color: 'white', 
              border: 'none', 
              borderRadius: '6px', 
              fontWeight: 700, 
              fontSize: '1rem',
              cursor: 'pointer',
              width: '100%',
              maxWidth: '300px'
            }}
          >
            🚨 EMERGENCY STOP
          </button>
        </div>
      </div>
    </section>
  );

  const renderLiveTradeFeed = () => {
    // Group trades by exchange
    const tradesByExchange = {
      luno: recentTrades.filter(t => t.exchange?.toLowerCase() === 'luno'),
      binance: recentTrades.filter(t => t.exchange?.toLowerCase() === 'binance'),
      kucoin: recentTrades.filter(t => t.exchange?.toLowerCase() === 'kucoin'),
      bybit: recentTrades.filter(t => t.exchange?.toLowerCase() === 'bybit'),
      kraken: recentTrades.filter(t => t.exchange?.toLowerCase() === 'kraken'),
      bitget: recentTrades.filter(t => t.exchange?.toLowerCase() === 'bitget'),
      gate: recentTrades.filter(t => t.exchange?.toLowerCase() === 'gate')
    };

    // Calculate stats per exchange
    const getExchangeStats = (trades) => {
      if (trades.length === 0) return { count: 0, winRate: 0, profit: 0 };
      const wins = trades.filter(t => t.is_profitable || t.profit_loss > 0).length;
      const profit = trades.reduce((sum, t) => sum + safeNumber(t.profit_loss, 0), 0);
      return {
        count: trades.length,
        winRate: safeToFixed((wins / trades.length) * 100, 1, '0.0'),
        profit: safeToFixed(profit, 2)
      };
    };
    
    // Use platform constants - single source of truth
    const allPlatforms = SUPPORTED_PLATFORMS.map(id => ({
      id: id,
      name: getPlatformDisplayName(id),
      icon: getPlatformIcon(id),
      supported: PLATFORM_CONFIG[id].enabled
    }));

    return (
      <section className="section active">
        <div className="card">
          <h2 style={{color: '#ffffff'}}>📊 Live Trades - Platform Comparison</h2>
          <p style={{color: 'var(--muted)', marginBottom: '20px', fontSize: '0.9rem'}}>
            Real-time trade feed showing all 7 supported platforms (Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io)
          </p>
          
          {/* 50/50 Split Layout: LEFT = Trade Feed | RIGHT = Platform Selector + Comparison */}
          <div style={{display: 'flex', gap: '16px', alignItems: 'stretch', minHeight: '600px'}}>
            
            {/* LEFT: Real-time Trade Feed */}
            <div style={{flex: '0 0 50%', display: 'flex', flexDirection: 'column'}}>
              <h3 style={{marginBottom: '12px', fontSize: '1.1rem'}}>Real-Time Trade Feed</h3>
              <div style={{
                flex: 1,
                background: 'var(--panel)', 
                borderRadius: '8px', 
                padding: '16px', 
                overflowY: 'auto',
                border: '1px solid var(--line)'
              }}>
                {recentTrades.length === 0 ? (
                  <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)'}}>
                    <p>📭 No trades yet. Trades will appear here in real-time.</p>
                  </div>
                ) : (
                  <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                    {recentTrades.slice(0, 30).map((trade, idx) => {
                      const isWin = trade.is_profitable || trade.profit_loss > 0;
                      const profitColor = isWin ? 'var(--success)' : 'var(--error)';
                      const profitIcon = isWin ? '🟢' : '🔴';
                      
                      return (
                        <div key={trade.id || trade.timestamp || `trade-${trade.symbol}-${idx}`} style={{
                          background: 'var(--bg)',
                          border: '1px solid ' + (isWin ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'),
                          borderRadius: '8px',
                          padding: '12px',
                          transition: 'all 0.2s'
                        }}>
                          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px'}}>
                            <div style={{fontWeight: 600, color: 'var(--text)', fontSize: '0.95rem'}}>
                              🤖 {trade.bot_name || 'Bot'}
                            </div>
                            <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                              {new Date(trade.timestamp).toLocaleTimeString()}
                            </div>
                          </div>
                          
                          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                            <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                              {trade.symbol} • {trade.exchange?.toUpperCase()}
                            </div>
                            <div style={{textAlign: 'right'}}>
                              <div style={{fontSize: '0.9rem', fontWeight: 700, color: profitColor}}>
                                {profitIcon} {isWin ? 'WIN' : 'LOSS'}
                              </div>
                              <div style={{fontSize: '0.85rem', color: profitColor, fontWeight: 600}}>
                                R{safeToFixed(trade.profit_loss, 2)}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
            
            {/* RIGHT: Platform Selector + Comparison Cards */}
            <div style={{flex: '0 0 50%', display: 'flex', flexDirection: 'column'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px'}}>
                <h3 style={{margin: 0, fontSize: '1.1rem'}}>Platform Performance</h3>
                <PlatformSelector 
                  value={platformFilter} 
                  onChange={setPlatformFilter}
                  includeAll={true}
                />
              </div>
              
              <div style={{
                flex: 1,
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px'
              }}>
                {allPlatforms
                  .filter(p => platformFilter === 'all' || p.id === platformFilter)
                  .map(platform => {
                    const stats = getExchangeStats(tradesByExchange[platform.id]);
                    const hasData = stats.count > 0;
                    
                    return (
                      <div key={platform.id} style={{
                        background: 'var(--glass)',
                        border: '1px solid var(--line)',
                        borderRadius: '12px',
                        padding: '20px',
                        transition: 'all 0.3s'
                      }}>
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
                          <h3 style={{margin: 0, textTransform: 'uppercase', fontSize: '1.1rem', color: 'var(--accent)'}}>
                            {platform.icon} {platform.name}
                          </h3>
                          <span style={{
                            padding: '4px 12px',
                            background: hasData ? 'rgba(16, 185, 129, 0.2)' : 'rgba(139, 139, 139, 0.2)',
                            color: hasData ? '#10b981' : '#8b8b8b',
                            borderRadius: '12px',
                            fontSize: '0.75rem',
                            fontWeight: 600
                          }}>
                            {hasData ? 'ACTIVE' : 'NO DATA'}
                          </span>
                        </div>
                        
                        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px'}}>
                          <div style={{textAlign: 'center'}}>
                            <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginBottom: '4px'}}>TRADES</div>
                            <div style={{fontSize: '1.4rem', fontWeight: 700, color: 'var(--text)'}}>{stats.count}</div>
                          </div>
                          <div style={{textAlign: 'center'}}>
                            <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginBottom: '4px'}}>WIN RATE</div>
                            <div style={{fontSize: '1.4rem', fontWeight: 700, color: hasData ? 'var(--success)' : 'var(--muted)'}}>{stats.winRate}%</div>
                          </div>
                          <div style={{textAlign: 'center'}}>
                            <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginBottom: '4px'}}>PROFIT</div>
                            <div style={{fontSize: '1.2rem', fontWeight: 700, color: parseFloat(stats.profit) >= 0 ? 'var(--success)' : 'var(--error)'}}>
                              R{stats.profit}
                            </div>
                          </div>
                        </div>
                        
                        {!hasData && (
                          <div style={{marginTop: '12px', padding: '8px', background: 'rgba(139, 139, 139, 0.1)', borderRadius: '6px', textAlign: 'center', fontSize: '0.8rem', color: 'var(--muted)'}}>
                            No trades yet for this platform
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  };

  const renderProfitGraphs = () => {
    
    const chartData = {
      labels: profitData?.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      datasets: [{
        label: 'Profit (ZAR)',
        data: profitData?.values || [0, 0, 0, 0, 0, 0, 0],
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.2)',
        fill: true,
        tension: 0.4,
        pointRadius: 5,
        pointHoverRadius: 8,
        pointBackgroundColor: '#10b981',
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2
      }]
    };
    
    const chartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 42, 0.95)',
          titleColor: '#10b981',
          bodyColor: '#ffffff',
          borderColor: '#10b981',
          borderWidth: 2,
          padding: 12,
          titleFont: { size: 14, weight: 'bold' },
          bodyFont: { size: 13 }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { 
            color: '#8b8b8b',
            font: { size: 11 },
            callback: function(value) {
              return 'R' + value;
            }
          },
          grid: { 
            color: 'rgba(255, 255, 255, 0.05)',
            drawBorder: false
          },
          border: { display: false }
        },
        x: {
          ticks: { 
            color: '#8b8b8b',
            font: { size: 11 }
          },
          grid: { 
            display: false
          },
          border: { display: false }
        }
      },
      interaction: {
        intersect: false,
        mode: 'index'
      }
    };
    
    return (
      <section className="section active">
        <div className="card">
          <h2 style={{marginBottom: '16px', color: '#ffffff'}}>💹 Profits & Performance</h2>
          
          {/* Horizontal Sub-tabs */}
          <div style={{
            display: 'flex', 
            gap: '10px', 
            marginBottom: '24px', 
            marginTop: '16px',
            borderBottom: '2px solid var(--line)', 
            paddingBottom: '10px',
            flexWrap: 'wrap'
          }}>
            <button 
              onClick={() => setProfitsTab('metrics')}
              style={{
                padding: '10px 20px',
                background: profitsTab === 'metrics' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (profitsTab === 'metrics' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: profitsTab === 'metrics' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: profitsTab === 'metrics' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: profitsTab === 'metrics' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              📊 Metrics
            </button>
            <button 
              onClick={() => setProfitsTab('profit-history')}
              style={{
                padding: '10px 20px',
                background: profitsTab === 'profit-history' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (profitsTab === 'profit-history' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: profitsTab === 'profit-history' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: profitsTab === 'profit-history' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: profitsTab === 'profit-history' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              💰 Profit History
            </button>
            <button 
              onClick={() => setProfitsTab('equity')}
              style={{
                padding: '10px 20px',
                background: profitsTab === 'equity' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (profitsTab === 'equity' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: profitsTab === 'equity' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: profitsTab === 'equity' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: profitsTab === 'equity' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              📈 Equity/PnL
            </button>
            <button 
              onClick={() => setProfitsTab('drawdown')}
              style={{
                padding: '10px 20px',
                background: profitsTab === 'drawdown' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (profitsTab === 'drawdown' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: profitsTab === 'drawdown' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: profitsTab === 'drawdown' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: profitsTab === 'drawdown' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              📉 Drawdown
            </button>
            <button 
              onClick={() => setProfitsTab('win-rate')}
              style={{
                padding: '10px 20px',
                background: profitsTab === 'win-rate' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (profitsTab === 'win-rate' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: profitsTab === 'win-rate' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: profitsTab === 'win-rate' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: profitsTab === 'win-rate' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🎯 Win Rate
            </button>
          </div>
          
          {/* Tab Content */}
          {profitsTab === 'metrics' && (
            <div style={{marginTop: '20px'}}>
              <ErrorBoundary title="Metrics Error" message="Unable to load metrics data.">
                <div>
                  <h3 style={{marginBottom: '16px'}}>📊 System Metrics</h3>
                  
                  {/* Horizontal Tabs */}
                  {/* Simplified - Keep only Flokx Alerts for traders */}
                  <div style={{marginBottom: '20px'}}>
                    <h3 style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                      📊 Market Alerts & Intelligence
                    </h3>
                  </div>

                  {/* Flokx Alerts Content */}
                  <div style={{marginTop: '20px'}}>
                    <ErrorBoundary title="Flokx Alerts Error" message="Unable to load Flokx alerts. Please check your API configuration.">
                      <div>
                        {!isFlokxActive && (
                          <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                              <p style={{color: 'var(--muted)', marginBottom: '12px'}}>
                                ⚠️ Flokx alerts are not active. Configure your Flokx API key in the API Setup section to enable real-time alerts.
                              </p>
                              {flokxStatus.last_error && (
                                <p style={{color: 'var(--error)', marginBottom: '12px', fontSize: '0.85rem'}}>
                                  Status check: {flokxStatus.last_error}
                                </p>
                              )}
                              <button 
                                onClick={() => showSection('api')}
                                style={{
                                  padding: '8px 16px',
                                  background: 'var(--accent2)',
                                  color: 'var(--text)',
                                  border: 'none',
                                  borderRadius: '6px',
                                  fontWeight: 600,
                                  cursor: 'pointer'
                                }}
                              >
                                Configure Flokx API
                              </button>
                            </div>
                          )}
                          
                          {isFlokxActive && (
                            <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                                <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                                  <div style={{width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)'}}></div>
                                  <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                    Flokx Active {flokxStatus.last_tested_at ? `• Last tested ${formatDate(flokxStatus.last_tested_at)}` : ''}
                                  </span>
                                </div>
                                <button 
                                  onClick={loadFlokxAlerts} 
                                  style={{
                                    padding: '6px 12px',
                                    borderRadius: '6px',
                                    background: 'var(--accent2)',
                                    color: 'var(--text)',
                                    border: 'none',
                                    fontWeight: 600,
                                    fontSize: '0.85rem',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Refresh Alerts
                                </button>
                              </div>
                              
                              <div style={{background: 'var(--glass)', padding: '12px', borderRadius: '6px', border: '1px solid var(--line)'}}>
                                {!Array.isArray(flokxAlerts) || flokxAlerts.length === 0 ? (
                                  <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                                    ✓ No alerts at this time - System running smoothly
                                  </p>
                                ) : (
                                  <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                                    {Array.isArray(flokxAlerts) && flokxAlerts.map((alert, idx) => (
                                      <div 
                                        key={idx}
                                        style={{
                                          padding: '12px',
                                          background: 'var(--panel)',
                                          borderRadius: '6px',
                                          borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                                          display: 'flex',
                                          justifyContent: 'space-between',
                                          alignItems: 'center'
                                        }}
                                      >
                                        <div>
                                          <div style={{fontWeight: 600, marginBottom: '4px'}}>
                                            {alert.title || alert.pair || 'Alert'}
                                          </div>
                                          <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                            {alert.message || 'No details available'}
                                          </div>
                                          <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                                            {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'No timestamp'}
                                          </div>
                                        </div>
                                        {(alert.priority || alert.type) && (
                                          <div style={{
                                            padding: '4px 8px',
                                            borderRadius: '4px',
                                            fontSize: '0.75rem',
                                            fontWeight: 600,
                                            background: getAlertColor(alert.priority || alert.type || 'info'),
                                            color: 'white'
                                          }}>
                                            {(alert.priority || alert.type || 'INFO').toUpperCase()}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </ErrorBoundary>
                    </div>
                  </div>
              </ErrorBoundary>
            </div>
          )}
          
          {profitsTab === 'profit-history' && (
            <div style={{marginTop: '20px'}}>
              {/* Header with period selector */}
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
                <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                  📊 Performance Analytics
                </h3>
                <div style={{display: 'flex', gap: '6px'}}>
                  {['daily', 'weekly', 'monthly'].map(period => (
                    <button 
                      key={period}
                      onClick={() => setGraphPeriod(period)}
                      style={{
                        padding: '6px 14px',
                        background: graphPeriod === period ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'var(--glass)',
                        color: graphPeriod === period ? '#ffffff' : 'var(--muted)',
                        border: graphPeriod === period ? 'none' : '1px solid var(--line)',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        textTransform: 'capitalize',
                        transition: 'all 0.3s'
                      }}
                    >
                      {period}
                    </button>
                  ))}
                </div>
              </div>
              
              {/* Stats Cards Row */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                <div style={{
                  padding: '16px',
                  background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  textAlign: 'center'
                }}>
                  <div style={{fontSize: '0.75rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Profit</div>
                  <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#10b981', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                    R{safeToFixed(profitData?.total, 2)}
                    <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>ZAR</span>
                  </div>
                </div>
                
                <div style={{
                  padding: '16px',
                  background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  textAlign: 'center'
                }}>
                  <div style={{fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Daily</div>
                  <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#3b82f6', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                    R{safeToFixed(profitData?.avg_daily, 2)}
                    <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{profitData?.avg_daily ? '+12%' : ''}</span>
                  </div>
                </div>
                
                <div style={{
                  padding: '16px',
                  background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  textAlign: 'center'
                }}>
                  <div style={{fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Best Day</div>
                  <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#f59e0b', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                    R{Number.isFinite(Number(profitData?.best_day))
                      ? safeToFixed(profitData.best_day, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                      : '0.00'}
                  </div>
                </div>
                
                <div style={{
                  padding: '16px',
                  background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(168, 85, 247, 0.3)',
                  textAlign: 'center'
                }}>
                  <div style={{fontSize: '0.75rem', color: '#a855f7', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Growth Rate</div>
                  <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#a855f7', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                    {safeToFixed(profitData?.growth_rate, 2)}%
                    <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{profitData?.growth_rate > 0 ? '↑' : ''}</span>
                  </div>
                </div>
              </div>
              
              {/* Chart */}
              <div style={{
                minHeight: '350px', 
                height: '350px',
                padding: '20px',
                background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                borderRadius: '10px',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
                display: 'flex',
                flexDirection: 'column'
              }}>
                {typeof window !== 'undefined' && (
                  <Line data={chartData} options={chartOptions} />
                )}
              </div>
            </div>
          )}
          
          {profitsTab === 'equity' && (
            <div style={{marginTop: '20px'}}>
              {/* Header with range selector */}
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
                <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                  📈 Equity & P/L Tracking
                </h3>
                <div style={{display: 'flex', gap: '6px'}}>
                  {['1d', '7d', '30d', '90d'].map(range => (
                    <button 
                      key={range}
                      onClick={() => setEquityRange(range)}
                      style={{
                        padding: '6px 14px',
                        background: equityRange === range ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'var(--glass)',
                        color: equityRange === range ? '#ffffff' : 'var(--muted)',
                        border: equityRange === range ? 'none' : '1px solid var(--line)',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        textTransform: 'uppercase',
                        transition: 'all 0.3s'
                      }}
                    >
                      {range}
                    </button>
                  ))}
                </div>
              </div>
              
              {equityData ? (
                <>
                  {/* Stats Cards Row */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Equity</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#10b981', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(equityData.current_equity, 2)}
                        <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>ZAR</span>
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total P&L</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: equityData.total_pnl >= 0 ? '#10b981' : '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(equityData.total_pnl, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Realized P&L</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#f59e0b', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(equityData.total_pnl, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Fees</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(equityData.total_fees, 2)}
                      </div>
                    </div>
                  </div>
                  
                  {/* Equity Curve Chart */}
                  <div style={{
                    minHeight: '350px', 
                    height: '350px',
                    padding: '20px',
                    background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
                    display: 'flex',
                    flexDirection: 'column'
                  }}>
                    {typeof window !== 'undefined' && equityData.equity_curve && equityData.equity_curve.length > 0 && (
                      <Line 
                        data={{
                          labels: equityData.equity_curve.map(p => new Date(p.timestamp).toLocaleDateString('en-ZA', {month: 'short', day: 'numeric'})),
                          datasets: [{
                            label: 'Equity (ZAR)',
                            data: equityData.equity_curve.map(p => p.equity),
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.2)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#10b981',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: {
                            legend: { display: false },
                            tooltip: {
                              backgroundColor: 'rgba(0, 0, 42, 0.95)',
                              titleColor: '#10b981',
                              bodyColor: '#ffffff',
                              borderColor: '#10b981',
                              borderWidth: 2,
                              padding: 12,
                              titleFont: { size: 14, weight: 'bold' },
                              bodyFont: { size: 13 },
                              callbacks: {
                                label: (context) => `Equity: R${safeToFixed(context.parsed.y, 2)}`
                              }
                            }
                          },
                          scales: {
                            y: {
                              beginAtZero: false,
                              ticks: { 
                                color: '#8b8b8b',
                                font: { size: 11 },
                                callback: (value) => 'R' + safeToFixed(value, 0, '0')
                              },
                              grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false }
                            },
                            x: {
                              ticks: { color: '#8b8b8b', font: { size: 10 }, maxRotation: 45, minRotation: 45 },
                              grid: { display: false }
                            }
                          }
                        }}
                      />
                    )}
                  </div>
                </>
              ) : (
                <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                    📊 No trade data available yet
                  </p>
                  <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                    Start trading to see your equity curve
                  </p>
                </div>
              )}
            </div>
          )}
          
          {profitsTab === 'drawdown' && (
            <div style={{marginTop: '20px'}}>
              {/* Header with range selector */}
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
                <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                  📉 Drawdown Analysis
                </h3>
                <div style={{display: 'flex', gap: '6px'}}>
                  {['1d', '7d', '30d', '90d'].map(range => (
                    <button 
                      key={range}
                      onClick={() => setDrawdownRange(range)}
                      style={{
                        padding: '6px 14px',
                        background: drawdownRange === range ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)' : 'var(--glass)',
                        color: drawdownRange === range ? '#ffffff' : 'var(--muted)',
                        border: drawdownRange === range ? 'none' : '1px solid var(--line)',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        textTransform: 'uppercase',
                        transition: 'all 0.3s'
                      }}
                    >
                      {range}
                    </button>
                  ))}
                </div>
              </div>
              
              {drawdownData ? (
                <>
                  {/* Stats Cards Row */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Max Drawdown</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {safeToFixed(drawdownData.max_drawdown_pct, 2)}%
                        <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>↓</span>
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Drawdown</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#f59e0b', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {safeToFixed(drawdownData.current_drawdown_pct, 2)}%
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Peak Equity</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#10b981', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(drawdownData.peak_equity, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Underwater Periods</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#3b82f6', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {drawdownData.underwater_periods || 0}
                      </div>
                    </div>
                  </div>
                  
                  {/* Drawdown Curve Chart */}
                  <div style={{
                    minHeight: '350px', 
                    height: '350px',
                    padding: '20px',
                    background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
                    display: 'flex',
                    flexDirection: 'column'
                  }}>
                    {typeof window !== 'undefined' && drawdownData.drawdown_curve && drawdownData.drawdown_curve.length > 0 ? (
                      <Line 
                        data={{
                          labels: drawdownData.drawdown_curve.map(p => new Date(p.timestamp).toLocaleDateString('en-ZA', {month: 'short', day: 'numeric'})),
                          datasets: [{
                            label: 'Drawdown %',
                            data: drawdownData.drawdown_curve.map(p => -p.drawdown_pct),
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.2)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 3,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#ef4444',
                            pointBorderColor: '#ffffff',
                            pointBorderWidth: 2
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: {
                            legend: { display: false },
                            tooltip: {
                              backgroundColor: 'rgba(0, 0, 42, 0.95)',
                              titleColor: '#ef4444',
                              bodyColor: '#ffffff',
                              borderColor: '#ef4444',
                              borderWidth: 2,
                              padding: 12,
                              titleFont: { size: 14, weight: 'bold' },
                              bodyFont: { size: 13 },
                              callbacks: {
                                label: (context) => `Drawdown: ${safeToFixed(Math.abs(context.parsed.y), 2)}%`
                              }
                            }
                          },
                          scales: {
                            y: {
                              reverse: false,
                              max: 0,
                              ticks: { 
                                color: '#8b8b8b',
                                font: { size: 11 },
                                callback: (value) => safeToFixed(Math.abs(value), 1, '0.0') + '%'
                              },
                              grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false }
                            },
                            x: {
                              ticks: { color: '#8b8b8b', font: { size: 10 }, maxRotation: 45, minRotation: 45 },
                              grid: { display: false }
                            }
                          }
                        }}
                      />
                    ) : (
                      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)'}}>
                        No drawdown data available
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                    📊 No trade data available yet
                  </p>
                  <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                    Start trading to see drawdown analysis
                  </p>
                </div>
              )}
            </div>
          )}
          
          {profitsTab === 'win-rate' && (
            <div style={{marginTop: '20px'}}>
              {/* Header with period selector */}
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
                <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                  🎯 Win Rate & Trade Statistics
                </h3>
                <div style={{display: 'flex', gap: '6px'}}>
                  {['today', '7d', '30d', 'all'].map(period => (
                    <button 
                      key={period}
                      onClick={() => setWinRatePeriod(period)}
                      style={{
                        padding: '6px 14px',
                        background: winRatePeriod === period ? 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)' : 'var(--glass)',
                        color: winRatePeriod === period ? '#ffffff' : 'var(--muted)',
                        border: winRatePeriod === period ? 'none' : '1px solid var(--line)',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        textTransform: 'capitalize',
                        transition: 'all 0.3s'
                      }}
                    >
                      {period}
                    </button>
                  ))}
                </div>
              </div>
              
              {winRateData && winRateData.total_trades > 0 ? (
                <>
                  {/* Stats Cards Grid */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(124, 58, 237, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#8b5cf6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Win Rate</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#8b5cf6', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {safeToFixed(winRateData.win_rate_pct, 1, '0.0')}%
                        <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>({winRateData.winning_trades}/{winRateData.total_trades})</span>
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Win</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#10b981', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(winRateData.avg_win, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Loss</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(winRateData.avg_loss, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Profit Factor</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#f59e0b', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {safeToFixed(winRateData.profit_factor, 2)}
                      </div>
                    </div>
                  </div>
                  
                  {/* Second Row */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Trades</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#3b82f6', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        {winRateData.total_trades || 0}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(22, 163, 74, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(34, 197, 94, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#22c55e', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Best Trade</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#22c55e', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(winRateData.best_trade, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(220, 38, 38, 0.1) 0%, rgba(185, 28, 28, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(220, 38, 38, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#dc2626', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Worst Trade</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#dc2626', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(winRateData.worst_trade, 2)}
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '16px',
                      background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%)',
                      borderRadius: '10px',
                      border: '1px solid rgba(168, 85, 247, 0.3)',
                      textAlign: 'center'
                    }}>
                      <div style={{fontSize: '0.75rem', color: '#a855f7', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total P&L</div>
                      <div style={{fontSize: '1.75rem', fontWeight: 700, color: winRateData.total_pnl >= 0 ? '#10b981' : '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                        R{safeToFixed(winRateData.total_pnl, 2)}
                      </div>
                    </div>
                  </div>
                  
                  {/* Win/Loss Breakdown */}
                  <div style={{
                    padding: '20px',
                    background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(139, 92, 246, 0.2)',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                  }}>
                    <h4 style={{margin: '0 0 16px 0', fontSize: '1rem', color: 'var(--text)'}}>Trade Distribution</h4>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px'}}>
                      <div>
                        <div style={{fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '8px'}}>Winning Trades</div>
                        <div style={{fontSize: '1.5rem', fontWeight: 700, color: '#10b981'}}>
                          {safeNumber(winRateData.winning_trades, 0)} ({safeToFixed((safeNumber(winRateData.winning_trades, 0) / Math.max(safeNumber(winRateData.total_trades, 0), 1)) * 100, 1, '0.0')}%)
                        </div>
                        <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px'}}>
                          Gross Profit: R{safeToFixed(winRateData.gross_profit, 2)}
                        </div>
                      </div>
                      <div>
                        <div style={{fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '8px'}}>Losing Trades</div>
                        <div style={{fontSize: '1.5rem', fontWeight: 700, color: '#ef4444'}}>
                          {safeNumber(winRateData.losing_trades, 0)} ({safeToFixed((safeNumber(winRateData.losing_trades, 0) / Math.max(safeNumber(winRateData.total_trades, 0), 1)) * 100, 1, '0.0')}%)
                        </div>
                        <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px'}}>
                          Gross Loss: R{safeToFixed(winRateData.gross_loss, 2)}
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                    📊 No trade data available yet
                  </p>
                  <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                    Start trading to see win rate statistics
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    );
  };

  const renderCountdown = () => {
    // Use countdown data from the new endpoint
    const countdownData = countdown || {};
    const progressDeg = countdownData.progress_pct ? (countdownData.progress_pct / 100) * 360 : 0;
    
    return (
      <section className="section active">
        <div className="card">
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px'}}>
            <h2 style={{margin: 0}}>🎯 Countdown to R1 Million</h2>
            <div style={{display: 'flex', gap: '8px', alignItems: 'center'}}>
              <span style={{
                padding: '6px 12px',
                background: countdownData.mode === 'live' ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                color: 'white',
                borderRadius: '6px',
                fontSize: '0.85rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                {countdownData.mode || 'Paper'} Mode
              </span>
            </div>
          </div>
          
          {countdownData.status === 'achieved' ? (
            <div style={{textAlign: 'center', padding: '60px 20px'}}>
              <div style={{fontSize: '5rem', marginBottom: '20px'}}>🎉</div>
              <div style={{fontSize: '2.5rem', fontWeight: 700, color: 'var(--success)', marginBottom: '15px'}}>
                TARGET ACHIEVED!
              </div>
              <div style={{fontSize: '1.3rem', color: 'var(--muted)'}}>
                You reached R1,000,000!
              </div>
            </div>
          ) : (
            <>
              {/* Main Stats Row */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginBottom: '24px'}}>
                {/* Days Remaining Card */}
                <div style={{
                  padding: '32px',
                  border: '2px solid var(--success)',
                  borderRadius: '12px',
                  textAlign: 'center',
                  background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.05) 100%)',
                  boxShadow: '0 4px 16px rgba(16, 185, 129, 0.2)'
                }}>
                  <div style={{fontSize: '4rem', fontWeight: 700, color: countdownData.days_remaining >= 9999 ? 'var(--error)' : 'var(--success)', margin: '12px 0', textShadow: '0 0 12px rgba(16, 185, 129, 0.5)'}}>
                    {countdownData.days_remaining < 9999 ? countdownData.days_remaining : '∞'}
                  </div>
                  <p style={{fontSize: '1rem', fontWeight: 600, color: 'var(--muted)', marginBottom: '4px'}}>
                    DAYS REMAINING
                  </p>
                  <p style={{fontSize: '1.5rem', fontWeight: 700, background: 'linear-gradient(45deg, var(--success), #34d399)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', margin: '8px 0'}}>
                    TO R1 MILLION
                  </p>
                </div>
                
                {/* Progress Circle Card */}
                <div style={{
                  padding: '32px',
                  border: '1px solid var(--line)',
                  borderRadius: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  alignItems: 'center',
                  background: 'var(--panel)'
                }}>
                  <div style={{width: '180px', height: '180px', borderRadius: '50%', background: `conic-gradient(var(--success) 0deg ${progressDeg}deg, var(--accent) ${progressDeg}deg 360deg)`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 24px rgba(16, 185, 129, 0.4)'}}>
                    <div style={{width: '140px', height: '140px', borderRadius: '50%', background: 'var(--panel)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', fontWeight: 700, color: 'var(--success)', flexDirection: 'column'}}>
                      <div>{safeToFixed(countdownData.progress_pct, 1, '0.0')}%</div>
                      <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginTop: '4px'}}>Complete</div>
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Key Metrics Grid */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px'}}>
                <div style={{padding: '20px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.3)'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Capital</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--success)'}}>
                    R{Number.isFinite(Number(countdownData.current_capital))
                      ? safeToFixed(countdownData.current_capital, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                      : '0.00'}
                  </div>
                </div>
                
                <div style={{padding: '20px', background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)', borderRadius: '10px', border: '1px solid rgba(59, 130, 246, 0.3)'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Daily ROI</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: '#3b82f6'}}>
                    {safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0.000')}%
                  </div>
                </div>
                
                <div style={{padding: '20px', background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)', borderRadius: '10px', border: '1px solid rgba(245, 158, 11, 0.3)'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Daily Profit</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: '#f59e0b'}}>
                    R{safeToFixed(countdownData.metrics?.avg_daily_profit, 2)}
                  </div>
                </div>
                
                <div style={{padding: '20px', background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%)', borderRadius: '10px', border: '1px solid rgba(168, 85, 247, 0.3)'}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Remaining</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: '#a855f7'}}>
                    R{Number.isFinite(Number(countdownData.remaining))
                      ? safeToFixed(countdownData.remaining, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                      : '1,000,000'}
                  </div>
                </div>
              </div>
              
              {/* Progress Bar */}
              <div style={{marginBottom: '24px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '0.9rem', fontWeight: 600}}>
                  <span style={{color: 'var(--text)'}}>R{Number.isFinite(Number(countdownData.current_capital))
                    ? safeToFixed(countdownData.current_capital, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                    : '0.00'}</span>
                  <span style={{color: 'var(--success)'}}>R1,000,000</span>
                </div>
                <div style={{height: '20px', background: 'var(--panel)', borderRadius: '10px', overflow: 'hidden', border: '2px solid var(--line)', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.1)'}}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(countdownData.progress_pct || 0, 100)}%`,
                    background: 'linear-gradient(90deg, var(--success) 0%, #34d399 50%, var(--accent) 100%)',
                    transition: 'width 1s ease-in-out',
                    boxShadow: '0 0 10px rgba(16, 185, 129, 0.5)',
                    position: 'relative'
                  }}>
                    <div style={{
                      position: 'absolute',
                      right: '10px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: 'white',
                      textShadow: '0 1px 2px rgba(0,0,0,0.5)'
                    }}>
                      {safeToFixed(countdownData.progress_pct, 1, '0.0')}%
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Details Grid */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '20px'}}>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Avg Daily Profit</div>
                  <div style={{fontSize: '1.3rem', fontWeight: 700, color: 'var(--success)'}}>
                    R{safeToFixed(countdownData.metrics?.avg_daily_profit, 2)}
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Total Trades</div>
                  <div style={{fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent)'}}>
                    {countdownData.metrics?.total_trades || 0}
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Est. Completion</div>
                  <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)'}}>
                    {countdownData.completion_date || 'Unknown'}
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Projection Type</div>
                  <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', textTransform: 'capitalize'}}>
                    {countdownData.projections?.using || 'N/A'}
                  </div>
                </div>
              </div>
              
              {/* 12-Month AI Projection */}
              {countdownData.projections?.twelve_month && (
                <div style={{marginTop: '20px', padding: '20px', background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)', borderRadius: '12px', border: '2px solid #3b82f6'}}>
                  <h3 style={{color: '#3b82f6', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                    🔮 AI 12-Month Projection
                  </h3>
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px'}}>
                    <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>Projected Value</div>
                      <div style={{fontSize: '1.6rem', fontWeight: 700, color: '#3b82f6'}}>
                        R{Number.isFinite(Number(countdownData.projections?.twelve_month))
                          ? safeToFixed(countdownData.projections.twelve_month, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                          : '0.00'}
                      </div>
                    </div>
                    <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>Expected Gain</div>
                      <div style={{fontSize: '1.6rem', fontWeight: 700, color: 'var(--success)'}}>
                        +R{Number.isFinite(Number(countdownData.projections?.twelve_month_gain))
                          ? safeToFixed(countdownData.projections.twelve_month_gain, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                          : '0.00'}
                      </div>
                    </div>
                    <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>12-Month ROI</div>
                      <div style={{fontSize: '1.6rem', fontWeight: 700, color: '#3b82f6'}}>
                        {safeToFixed(countdownData.projections?.twelve_month_roi, 1, '0.0')}%
                      </div>
                    </div>
                  </div>
                  <div style={{marginTop: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--muted)', textAlign: 'center'}}>
                    💡 Based on current {safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0')}% daily ROI with compound interest over 365 days
                  </div>
                </div>
              )}
              
              <div style={{marginTop: '16px', padding: '16px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.05) 100%)', borderRadius: '8px', border: '2px solid var(--success)', textAlign: 'center'}}>
                <p style={{margin: 0, fontSize: '1rem', color: 'var(--text)', fontWeight: 600}}>
                  {countdownData.message || 'Keep trading to reach your goal!'}
                </p>
              </div>
              
              <div style={{marginTop: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--line)', fontSize: '0.85rem', color: 'var(--muted)'}}>
                <p><strong>How it works:</strong> Based on your current capital (R{Number.isFinite(Number(countdownData.current_capital))
                  ? safeToFixed(countdownData.current_capital, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                  : '0.00'}) and daily ROI ({safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0')}%), the system uses compound interest calculations to project your path to R1,000,000. Updates in real-time as you trade!</p>
              </div>
            </>
          )}
          
          {/* Custom User Countdowns */}
          <div style={{marginTop: '40px', paddingTop: '30px', borderTop: '2px solid var(--line)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px'}}>
              <h3 style={{fontSize: '1.3rem', fontWeight: 600, color: 'var(--text)'}}>
                🎯 Your Custom Goals
              </h3>
              {customCountdowns.length < 2 && (
                <button
                  onClick={() => setShowAddCountdown(!showAddCountdown)}
                  style={{
                    padding: '8px 16px',
                    background: showAddCountdown ? 'var(--error)' : 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.9rem'
                  }}
                >
                  {showAddCountdown ? '✖ Cancel' : '➕ Add Goal'}
                </button>
              )}
            </div>
            
            {/* Add Countdown Form */}
            {showAddCountdown && (
              <div style={{
                marginBottom: '20px',
                padding: '20px',
                background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(124, 58, 237, 0.05) 100%)',
                borderRadius: '12px',
                border: '2px solid #8b5cf6'
              }}>
                <h4 style={{marginBottom: '16px', color: '#8b5cf6'}}>Add New Goal</h4>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '12px', alignItems: 'end'}}>
                  <div>
                    <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>
                      Goal Label
                    </label>
                    <input
                      type="text"
                      value={newCountdownLabel}
                      onChange={(e) => setNewCountdownLabel(e.target.value)}
                      placeholder="e.g., BMW M3"
                      maxLength={50}
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '6px',
                        border: '1px solid var(--line)',
                        background: 'var(--panel)',
                        color: 'var(--text)',
                        fontSize: '0.95rem'
                      }}
                    />
                  </div>
                  <div>
                    <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>
                      Target Amount (ZAR)
                    </label>
                    <input
                      type="number"
                      value={newCountdownAmount}
                      onChange={(e) => setNewCountdownAmount(e.target.value)}
                      placeholder="e.g., 1340000"
                      min="1"
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '6px',
                        border: '1px solid var(--line)',
                        background: 'var(--panel)',
                        color: 'var(--text)',
                        fontSize: '0.95rem'
                      }}
                    />
                  </div>
                  <button
                    onClick={addCustomCountdown}
                    style={{
                      padding: '10px 20px',
                      background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      height: '42px'
                    }}
                  >
                    ✓ Add
                  </button>
                </div>
              </div>
            )}
            
            {/* Display Custom Countdowns */}
            {customCountdowns.length === 0 ? (
              <div style={{
                padding: '40px 20px',
                textAlign: 'center',
                background: 'var(--panel)',
                borderRadius: '12px',
                border: '1px solid var(--line)'
              }}>
                <div style={{fontSize: '3rem', marginBottom: '12px'}}>🎯</div>
                <p style={{color: 'var(--muted)', fontSize: '1rem'}}>
                  No custom goals yet. Add up to 2 personal financial targets!
                </p>
                <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginTop: '8px'}}>
                  Track your progress towards that dream car, house, or any goal.
                </p>
              </div>
            ) : (
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px'}}>
                {customCountdowns.map((cd) => {
                  const progressDeg = (cd.progress_pct / 100) * 360;
                  return (
                    <div key={cd.id} style={{
                      padding: '24px',
                      background: 'var(--panel)',
                      borderRadius: '12px',
                      border: '2px solid var(--accent)',
                      position: 'relative'
                    }}>
                      <button
                        onClick={() => deleteCustomCountdown(cd.id)}
                        style={{
                          position: 'absolute',
                          top: '12px',
                          right: '12px',
                          padding: '4px 8px',
                          background: 'var(--error)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                          fontWeight: 600
                        }}
                      >
                        ✖
                      </button>
                      
                      <h4 style={{fontSize: '1.2rem', fontWeight: 700, color: 'var(--text)', marginBottom: '16px'}}>
                        {cd.label}
                      </h4>
                      
                      <div style={{textAlign: 'center', marginBottom: '16px'}}>
                        <div style={{fontSize: '3rem', fontWeight: 700, color: cd.days_remaining >= 9999 ? 'var(--error)' : 'var(--accent)'}}>
                          {cd.days_remaining < 9999 ? cd.days_remaining : '∞'}
                        </div>
                        <div style={{fontSize: '0.85rem', color: 'var(--muted)', fontWeight: 600}}>
                          DAYS REMAINING
                        </div>
                      </div>
                      
                      {/* Progress Bar */}
                      <div style={{marginBottom: '16px'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.85rem'}}>
                          <span>R{safeToFixed(cd.current_progress, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</span>
                          <span style={{color: 'var(--accent)', fontWeight: 600}}>
                            {safeToFixed(cd.progress_pct, 1, '0.0')}%
                          </span>
                          <span>R{safeToFixed(cd.target_amount, 0, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</span>
                        </div>
                        <div style={{
                          height: '12px',
                          background: 'var(--glass)',
                          borderRadius: '6px',
                          overflow: 'hidden',
                          border: '1px solid var(--line)'
                        }}>
                          <div style={{
                            height: '100%',
                            width: `${Math.min(cd.progress_pct, 100)}%`,
                            background: 'linear-gradient(90deg, var(--accent) 0%, #ec4899 100%)',
                            transition: 'width 1s ease-in-out'
                          }}></div>
                        </div>
                      </div>
                      
                      <div style={{
                        padding: '12px',
                        background: 'var(--glass)',
                        borderRadius: '6px',
                        border: '1px solid var(--line)',
                        fontSize: '0.85rem',
                        color: 'var(--muted)',
                        textAlign: 'center'
                      }}>
                        R{safeToFixed(cd.remaining, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')} remaining
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </section>
    );
  };

  const renderWalletHub = () => {
    return (
      <section className="section active">
        <div className="card">
          <WalletHub />
        </div>
      </section>
    );
  };

  const renderDecisionTrace = () => {
    return (
      <section className="section active">
        <div className="card">
          <DecisionTrace />
        </div>
      </section>
    );
  };

  const renderWhaleFlow = () => {
    return (
      <section className="section active">
        <div className="card">
          <WhaleFlowHeatmap />
        </div>
      </section>
    );
  };

  const renderMetrics = () => {
    return (
      <section className="section active">
        <div className="card">
          <PrometheusMetrics />
        </div>
      </section>
    );
  };

  // Combined Intelligence section with tabs
  const renderIntelligence = () => {
    return (
      <section className="section active">
        <div className="card">
          <h2>🧠 Intelligence Dashboard</h2>
          
          {/* Intelligence Tabs */}
          <div style={{display: 'flex', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '10px'}}>
            <button 
              onClick={() => setIntelligenceTab('whale-flow')}
              style={{
                padding: '8px 16px',
                background: intelligenceTab === 'whale-flow' ? 'rgba(74, 144, 226, 0.3)' : 'transparent',
                border: '1px solid ' + (intelligenceTab === 'whale-flow' ? '#4a90e2' : 'rgba(255,255,255,0.2)'),
                borderRadius: '6px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: intelligenceTab === 'whale-flow' ? 'bold' : 'normal'
              }}
            >
              🐋 Whale Flow
            </button>
            <button 
              onClick={() => setIntelligenceTab('decision-trace')}
              style={{
                padding: '8px 16px',
                background: intelligenceTab === 'decision-trace' ? 'rgba(74, 144, 226, 0.3)' : 'transparent',
                border: '1px solid ' + (intelligenceTab === 'decision-trace' ? '#4a90e2' : 'rgba(255,255,255,0.2)'),
                borderRadius: '6px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: intelligenceTab === 'decision-trace' ? 'bold' : 'normal'
              }}
            >
              🎬 Decision Trace
            </button>
            <button 
              onClick={() => setIntelligenceTab('metrics')}
              style={{
                padding: '8px 16px',
                background: intelligenceTab === 'metrics' ? 'rgba(74, 144, 226, 0.3)' : 'transparent',
                border: '1px solid ' + (intelligenceTab === 'metrics' ? '#4a90e2' : 'rgba(255,255,255,0.2)'),
                borderRadius: '6px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: intelligenceTab === 'metrics' ? 'bold' : 'normal'
              }}
            >
              📊 Metrics
            </button>
          </div>

          {/* Tab Content */}
          {intelligenceTab === 'whale-flow' && <WhaleFlowHeatmap />}
          {intelligenceTab === 'decision-trace' && <DecisionTrace />}
          {intelligenceTab === 'metrics' && <PrometheusMetrics />}
        </div>
      </section>
    );
  };

  const renderAPIKeys = () => {
    return (
      <section className="section active">
        <div className="card">
          <APIKeySettings />
        </div>
      </section>
    );
  };

  // New unified Metrics section with tabs
  const renderMetricsWithTabs = () => {
    return (
      <section className="section active">
        <div className="card">
          <h2>📊 Metrics Dashboard</h2>
          
          {/* Horizontal Tabs */}
          <div style={{
            display: 'flex', 
            gap: '10px', 
            marginBottom: '24px', 
            marginTop: '16px',
            borderBottom: '2px solid var(--line)', 
            paddingBottom: '10px',
            flexWrap: 'wrap'
          }}>
            <button 
              onClick={() => setMetricsTab('flokx')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'flokx' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'flokx' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'flokx' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'flokx' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'flokx' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🔔 Flokx Alerts
            </button>
            <button 
              onClick={() => setMetricsTab('decision-trace')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'decision-trace' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'decision-trace' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'decision-trace' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'decision-trace' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'decision-trace' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🎬 Decision Trace
            </button>
            <button 
              onClick={() => setMetricsTab('whale-flow')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'whale-flow' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'whale-flow' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'whale-flow' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'whale-flow' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'whale-flow' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🐋 Whale Flow
            </button>
            <button 
              onClick={() => setMetricsTab('system-metrics')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'system-metrics' ? 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'system-metrics' ? '#4a90e2' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'system-metrics' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'system-metrics' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'system-metrics' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              📊 System Metrics
            </button>
          </div>

          {/* Tab Content */}
          <div style={{marginTop: '20px'}}>
            {metricsTab === 'flokx' && (
              <ErrorBoundary title="Flokx Alerts Error" message="Unable to load Flokx alerts. Please check your API configuration.">
                <div>
                  {!isFlokxActive && (
                    <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                      <p style={{color: 'var(--muted)', marginBottom: '12px'}}>
                        ⚠️ Flokx alerts are not active. Configure your Flokx API key in the API Setup section to enable real-time alerts.
                      </p>
                      {flokxStatus.last_error && (
                        <p style={{color: 'var(--error)', marginBottom: '12px', fontSize: '0.85rem'}}>
                          Status check: {flokxStatus.last_error}
                        </p>
                      )}
                      <button 
                        onClick={() => showSection('api')}
                        style={{
                          padding: '8px 16px',
                          background: 'var(--accent2)',
                          color: 'var(--text)',
                          border: 'none',
                          borderRadius: '6px',
                          fontWeight: 600,
                          cursor: 'pointer'
                        }}
                      >
                        Configure Flokx API
                      </button>
                    </div>
                  )}
                  
                  {isFlokxActive && (
                    <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                        <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                          <div style={{width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)'}}></div>
                          <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                            Flokx Active {flokxStatus.last_tested_at ? `• Last tested ${formatDate(flokxStatus.last_tested_at)}` : ''}
                          </span>
                        </div>
                        <button 
                          onClick={loadFlokxAlerts} 
                          style={{
                            padding: '6px 12px',
                            borderRadius: '6px',
                            background: 'var(--accent2)',
                            color: 'var(--text)',
                            border: 'none',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                            cursor: 'pointer'
                          }}
                        >
                          Refresh Alerts
                        </button>
                      </div>
                      
                      <div style={{background: 'var(--glass)', padding: '12px', borderRadius: '6px', border: '1px solid var(--line)'}}>
                        {!Array.isArray(flokxAlerts) || flokxAlerts.length === 0 ? (
                          <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                            ✓ No alerts at this time - System running smoothly
                          </p>
                        ) : (
                          <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                            {Array.isArray(flokxAlerts) && flokxAlerts.map((alert, idx) => (
                              <div 
                                key={idx}
                                style={{
                                  padding: '12px',
                                  background: 'var(--panel)',
                                  borderRadius: '6px',
                                  borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center'
                                }}
                              >
                                <div>
                                  <div style={{fontWeight: 600, marginBottom: '4px'}}>
                                    {alert.title || alert.pair || 'Alert'}
                                  </div>
                                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                    {alert.message || 'No details available'}
                                  </div>
                                  <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                                    {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'No timestamp'}
                                  </div>
                                </div>
                                {(alert.priority || alert.type) && (
                                  <div style={{
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: getAlertColor(alert.priority || alert.type || 'info'),
                                    color: 'white'
                                  }}>
                                    {(alert.priority || alert.type || 'INFO').toUpperCase()}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </ErrorBoundary>
            )}
            {metricsTab === 'decision-trace' && (
              <ErrorBoundary title="Decision Trace Error" message="Unable to load decision trace. The service may be unavailable.">
                <DecisionTrace />
              </ErrorBoundary>
            )}
            {metricsTab === 'whale-flow' && (
              <ErrorBoundary title="Whale Flow Error" message="Unable to load whale flow heatmap. Data may be unavailable.">
                <WhaleFlowHeatmap />
              </ErrorBoundary>
            )}
            {metricsTab === 'system-metrics' && (
              <ErrorBoundary title="System Metrics Error" message="Unable to load system metrics. Prometheus may not be configured.">
                <PrometheusMetrics />
              </ErrorBoundary>
            )}
          </div>
        </div>
      </section>
    );
  };

  const renderFlokxAlerts = () => {
    
    return (
      <section className="section active">
        <div className="card">
          <h2>Flokx Alerts</h2>
          
          {!isFlokxActive && (
            <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
              <p style={{color: 'var(--muted)', marginBottom: '12px'}}>
                ⚠️ Flokx alerts are not active. Configure your Flokx API key in the API Setup section to enable real-time alerts.
              </p>
              {flokxStatus.last_error && (
                <p style={{color: 'var(--error)', marginBottom: '12px', fontSize: '0.85rem'}}>
                  Status check: {flokxStatus.last_error}
                </p>
              )}
              <button 
                onClick={() => showSection('api')}
                style={{
                  padding: '8px 16px',
                  background: 'var(--accent2)',
                  color: 'var(--text)',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Configure Flokx API
              </button>
            </div>
          )}
          
          {isFlokxActive && (
            <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                  <div style={{width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)'}}></div>
                  <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                    Flokx Active {flokxStatus.last_tested_at ? `• Last tested ${formatDate(flokxStatus.last_tested_at)}` : ''}
                  </span>
                </div>
                <button 
                  onClick={loadFlokxAlerts} 
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    background: 'var(--accent2)',
                    color: 'var(--text)',
                    border: 'none',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: 'pointer'
                  }}
                >
                  Refresh Alerts
                </button>
              </div>
              
              <div style={{background: 'var(--glass)', padding: '12px', borderRadius: '6px', border: '1px solid var(--line)'}}>
                {!Array.isArray(flokxAlerts) || flokxAlerts.length === 0 ? (
                  <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                    ✓ No alerts at this time - System running smoothly
                  </p>
                ) : (
                  <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                    {Array.isArray(flokxAlerts) && flokxAlerts.map((alert, idx) => (
                      <div 
                        key={idx}
                        style={{
                          padding: '12px',
                          background: 'var(--panel)',
                          borderRadius: '6px',
                          borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center'
                        }}
                      >
                        <div>
                          <div style={{fontWeight: 600, marginBottom: '4px'}}>
                            {alert.title || alert.pair || 'Alert'}
                          </div>
                          <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                            {alert.message || 'No details available'}
                          </div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                            {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'No timestamp'}
                          </div>
                        </div>
                        {(alert.priority || alert.type) && (
                          <div style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: getAlertColor(alert.priority || alert.type || 'info'),
                            color: 'white'
                          }}>
                            {(alert.priority || alert.type || 'INFO').toUpperCase()}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    );
  };

  return (
    <div className="app">
      {/* Sidebar - Desktop */}
      {!isMobile && (
        <aside className="sidebar">
          <img
            src="/assets/logo.png"
            className="logo"
            alt="Logo"
            onClick={() => showSection('overview')}
            style={{ cursor: 'pointer' }}
          />
          <nav className="nav" key={`nav-${showAdmin}`}>
            <a href="#" className={activeSection === 'welcome' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('welcome'); }}>🚀 Welcome</a>
            <a href="#" className={activeSection === 'api' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('api'); }}>🔑 API Setup</a>
            <a href="#" className={activeSection === 'bots' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('bots'); }}>🤖 Bot Management</a>
            <a href="#" className={activeSection === 'system' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('system'); }}>🎮 System Mode</a>
            <a href="#" className={activeSection === 'graphs' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('graphs'); }}>💹 Profits & Performance</a>
            <a href="#" className={activeSection === 'trades' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('trades'); }}>📊 Live Trades</a>
            <a href="#" className={activeSection === 'countdown' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('countdown'); }}>⏱️ Countdown</a>
            <a href="#" className={activeSection === 'wallet' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('wallet'); }}>💰 Wallet Hub</a>
            <a href="#" className={activeSection === 'profile' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('profile'); }}>👤 Profile</a>
            {showAdmin && (
              <a href="#" className={activeSection === 'admin' ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection('admin'); }}>🔧 Admin</a>
            )}
          </nav>
        </aside>
      )}

      {/* Topbar - Desktop */}
      {!isMobile && (
        <header className="topbar">
          <h1>Amarktai Network</h1>
          <div className="top-actions">
            <div className="status-indicator" style={{padding: '4px 12px', background: systemHealth.errors === 0 && connectionStatus.api === 'Connected' ? 'var(--success)' : 'var(--error)', borderRadius: '6px', fontWeight: 600}}>
              <span>{systemHealth.errors === 0 && connectionStatus.api === 'Connected' ? '✓ System Healthy' : '⚠ System Issues'}</span>
            </div>
            <div className="status-indicator">
              <span>API</span>
              <div className={`status-dot ${connectionStatus.api === 'Connected' ? 'ok' : 'err'}`}></div>
            </div>
            <div className="status-indicator">
              <span>SSE</span>
              <div className={`status-dot ${connectionStatus.sse === 'Connected' ? 'ok' : 'err'}`}></div>
            </div>
            <div className="status-indicator">
              <span>WS</span>
              <span style={{
                marginLeft: '4px',
                color: connectionStatus.ws === 'Connected' ? 'var(--success)' : 'var(--muted)',
                fontWeight: 600
              }}>
                {connectionStatus.ws === 'Connected' ? 'Connected' : 'Disconnected'}
              </span>
              <div className={`status-dot ${connectionStatus.ws === 'Connected' ? 'ok' : 'err'}`}></div>
            </div>
            <div className="status-indicator">
              <span>RTT: {wsRtt}</span>
            </div>
            <button className="logout-btn" onClick={handleLogout}>Logout</button>
          </div>
        </header>
      )}

      {/* Mobile Topbar */}
      {isMobile && (
        <div className="mobile-topbar">
          <button className="mobile-logo-btn" onClick={() => showSection('overview')}>
            <img
              src="/assets/logo.png"
              className="mobile-logo"
              alt="Logo"
            />
          </button>
          <div className="mobile-btns">
            <button className="mobile-btn" onClick={() => showSection('welcome')}>Welcome</button>
            <button className="mobile-btn" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="main"> 
        {activeSection === 'welcome' && renderWelcome()}
        {activeSection === 'overview' && renderOverview()}
        {activeSection === 'api' && renderApiSetup()}
        {activeSection === 'bots' && renderBots()}
        {activeSection === 'system' && renderSystemMode()}
        {activeSection === 'graphs' && renderProfitGraphs()}
        {activeSection === 'trades' && renderLiveTradeFeed()}
        {activeSection === 'countdown' && renderCountdown()}
        {activeSection === 'wallet' && renderWalletHub()}
        {activeSection === 'profile' && renderProfile()}
        {activeSection === 'admin' && showAdmin && renderAdmin()}
      </main>

      {/* Footer */}
      <footer className="footer">
        <div>© 2026 Amarktai Network. All rights reserved.</div>
        {/* TASK G - Only show build badge in admin view */}
        {showAdmin && <VersionBadge position="footer" showBuildInfo={true} />}
      </footer>

      {/* Bot Promotion Modal */}
      {showPromotionModal && eligibleBots.length > 0 && (
        <div className="modal-overlay" onClick={() => setShowPromotionModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>🎉 Bots Ready for Live Trading!</h2>
            <p style={{marginBottom: '20px'}}>
              {eligibleBots.length} bot(s) have completed their 7-day paper trading period and are eligible for live trading.
            </p>
            <div style={{marginBottom: '20px', textAlign: 'left', background: '#1a1a2e', padding: '15px', borderRadius: '8px'}}>
              <h3 style={{marginBottom: '10px', fontSize: '16px'}}>Eligible Bots:</h3>
              {eligibleBots.map(bot => (
                <div key={bot.id} style={{padding: '8px 0', borderBottom: '1px solid #333'}}>
                  <strong>{bot.name}</strong> - Capital: R{safeToFixed(bot.current_capital, 2)}, Profit: R{safeToFixed(bot.profit, 2)}
                </div>
              ))}
            </div>
            <div style={{marginBottom: '20px', textAlign: 'left', background: '#2a2a3e', padding: '15px', borderRadius: '8px'}}>
              <h3 style={{marginBottom: '10px', fontSize: '16px', color: '#ffcc00'}}>⚠️ Important Questions:</h3>
              <ol style={{paddingLeft: '20px'}}>
                <li style={{marginBottom: '8px'}}>Have you funded your LUNO wallet with real ZAR?</li>
                <li style={{marginBottom: '8px'}}>Do you want to use these paper-trained bots for live trading?</li>
                <li>Are you ready to trade with real money?</li>
              </ol>
            </div>
            <div style={{display: 'flex', gap: '10px', justifyContent: 'center'}}>
              <button
                className="btn-primary"
                onClick={() => confirmLiveSwitch(true, true)}
                style={{background: '#00ff88', color: '#000', padding: '12px 24px'}}
              >
                ✅ Yes, I've Funded LUNO - Switch to Live!
              </button>
              <button
                className="btn-danger"
                onClick={() => {
                  setShowPromotionModal(false);
                  toast.info('Please fund your LUNO wallet before enabling live trading');
                }}
                style={{padding: '12px 24px'}}
              >
                ❌ Not Yet - Keep Paper Trading
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
