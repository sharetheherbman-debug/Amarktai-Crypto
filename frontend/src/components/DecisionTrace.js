import { useState, useEffect, useRef, useMemo } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import './DecisionTrace.css';

/**
 * DecisionTrace Component
 * 
 * Provides a DVR-like replay interface for viewing agent reasoning steps
 * Consumes unified real-time stream of trading decisions with full provenance
 * Allows stepping through historical decisions and understanding AI logic
 */
export default function DecisionTrace() {
  const [decisions, setDecisions] = useState([]);
  const [bots, setBots] = useState([]);
  const [selectedBotId, setSelectedBotId] = useState('all');
  const [selectedDecision, setSelectedDecision] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [filter, setFilter] = useState('all'); // all, buy, sell, neutral
  const [loading, setLoading] = useState(true);
  const playbackIntervalRef = useRef(null);
  const lastUpdate = useLastUpdate('decisions');

  // Load initial decisions
  useEffect(() => {
    loadBots();
    loadInitialDecisions();
  }, []);

  useEffect(() => {
    loadInitialDecisions();
  }, [selectedBotId]);

  const loadBots = async () => {
    try {
      const data = await get('/bots/status');
      setBots(Array.isArray(data?.bots) ? data.bots : []);
    } catch (error) {
      console.error('Failed to load bots for decision trace:', error);
    }
  };

  const loadInitialDecisions = async () => {
    try {
      const botFilter = selectedBotId && selectedBotId !== 'all' ? `&bot_id=${encodeURIComponent(selectedBotId)}` : '';
      const data = await get(`/advanced/decisions/recent?limit=20${botFilter}`);
      setDecisions(data.decisions || []);
      setSelectedDecision((data.decisions || [])[0] || null);
      setCurrentIndex(0);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load decisions:', error);
      setLoading(false);
    }
  };

  // Subscribe to real-time decision updates
  useRealtimeEvent('decisions', (decision) => {
    setDecisions(prev => {
      const updated = [decision, ...prev];
      // Keep last 100 decisions
      return updated.slice(0, 100);
    });
  }, []);

  // Use useMemo to declare filteredDecisions BEFORE it's used in useEffect
  const filteredDecisions = useMemo(() => {
    return decisions.filter(d => {
      if (filter === 'all') return true;
      return d.decision?.toLowerCase() === filter;
    });
  }, [decisions, filter]);

  // DVR playback functionality
  useEffect(() => {
    if (isPlaying && filteredDecisions.length > 0) {
      playbackIntervalRef.current = setInterval(() => {
        setCurrentIndex(prev => {
          const next = prev + 1;
          if (next >= filteredDecisions.length) {
            setIsPlaying(false);
            return prev;
          }
          setSelectedDecision(filteredDecisions[next]);
          return next;
        });
      }, 2000); // 2 seconds per decision
    } else if (playbackIntervalRef.current) {
      clearInterval(playbackIntervalRef.current);
      playbackIntervalRef.current = null;
    }
    
    return () => {
      if (playbackIntervalRef.current) {
        clearInterval(playbackIntervalRef.current);
      }
    };
  }, [isPlaying, filteredDecisions]);

  const handlePlayPause = () => {
    setIsPlaying(!isPlaying);
  };

  const handleStop = () => {
    setIsPlaying(false);
    setCurrentIndex(0);
    setSelectedDecision(filteredDecisions[0] || null);
  };

  const handleStepForward = () => {
    if (currentIndex < filteredDecisions.length - 1) {
      const next = currentIndex + 1;
      setCurrentIndex(next);
      setSelectedDecision(filteredDecisions[next]);
    }
  };

  const handleStepBackward = () => {
    if (currentIndex > 0) {
      const prev = currentIndex - 1;
      setCurrentIndex(prev);
      setSelectedDecision(filteredDecisions[prev]);
    }
  };

  const handleDecisionClick = (decision, index) => {
    setSelectedDecision(decision);
    setCurrentIndex(index);
    setIsPlaying(false);
  };

  const getDecisionColor = (decision) => {
    const d = decision?.toLowerCase() || 'neutral';
    if (d.includes('buy')) return 'text-green-600 bg-green-50';
    if (d.includes('sell')) return 'text-red-600 bg-red-50';
    return 'text-gray-600 bg-gray-50';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.8) return 'text-green-600';
    if (confidence >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="decision-trace-container">
      {/* Header with controls */}
      <div className="decision-trace-header">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold">Decision Trace</h2>
            <p className="text-sm text-gray-500">AI Trading Decision Provenance</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={lastUpdate ? 'default' : 'destructive'}>
              {lastUpdate ? '🟢 Live' : '🔴 Waiting'}
            </Badge>
            {lastUpdate && (
              <span className="text-xs text-muted-foreground">
                {new Date(lastUpdate).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        {/* DVR Controls */}
          <div className="dvr-controls flex items-center gap-2 mb-4">
          <button
            onClick={handleStop}
            className="control-btn"
            disabled={filteredDecisions.length === 0}
            title="Stop"
          >
            ⏹️
          </button>
          <button
            onClick={handleStepBackward}
            className="control-btn"
            disabled={currentIndex <= 0}
            title="Step Back"
          >
            ⏮️
          </button>
          <button
            onClick={handlePlayPause}
            className="control-btn play-pause"
            disabled={filteredDecisions.length === 0}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? '⏸️' : '▶️'}
          </button>
          <button
            onClick={handleStepForward}
            className="control-btn"
            disabled={currentIndex >= filteredDecisions.length - 1}
            title="Step Forward"
          >
            ⏭️
          </button>
          
          {/* Filter */}
            <div className="ml-auto flex gap-2">
              <select
                value={selectedBotId}
                onChange={(e) => setSelectedBotId(e.target.value)}
                className="filter-select"
              >
                <option value="all">All Bots</option>
                {bots.map((bot) => (
                  <option key={bot.id} value={bot.id}>
                    {bot.name || `Bot ${bot.id}`} ({bot.exchange || 'unknown'})
                  </option>
                ))}
              </select>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              className="filter-select"
            >
              <option value="all">All Decisions</option>
              <option value="buy">Buy Only</option>
              <option value="sell">Sell Only</option>
              <option value="neutral">Neutral Only</option>
            </select>
          </div>
        </div>

        {/* Progress bar */}
        {filteredDecisions.length > 0 && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${((currentIndex + 1) / filteredDecisions.length) * 100}%` }}
              />
            </div>
            <span className="progress-text">
              {currentIndex + 1} / {filteredDecisions.length}
            </span>
          </div>
        )}
      </div>

      {/* Main content area */}
      <div className="decision-trace-content">
        {/* Timeline sidebar */}
        <div className="timeline-sidebar">
          <h3 className="text-sm font-semibold mb-2">Decision Timeline</h3>
          <div className="timeline-list">
            {filteredDecisions.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No decisions yet. Waiting for trades...
              </p>
            ) : (
              filteredDecisions.map((decision, idx) => (
                <div
                  key={idx}
                  className={`timeline-item ${idx === currentIndex ? 'active' : ''}`}
                  onClick={() => handleDecisionClick(decision, idx)}
                >
                  <div className="timeline-marker" />
                  <div className="timeline-content">
                    <div className="flex items-center justify-between">
                      <span className={`font-semibold text-xs ${getDecisionColor(decision.decision)}`}>
                        {decision.decision?.toUpperCase() || 'NEUTRAL'}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(decision.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      {decision.symbol || 'BTC/USDT'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Regime: {decision.regime || decision.market_regime || 'unknown'} •
                      Confidence: {decision.confidence != null ? `${(Number(decision.confidence) * 100).toFixed(0)}%` : '—'} •
                      Expectancy: {decision.expectancy_net_edge_pct != null ? `${Number(decision.expectancy_net_edge_pct).toFixed(2)}%` : '—'}
                    </div>
                    <div className="text-xs text-gray-500">
                      Outcome: {decision.execution || decision.outcome || decision.decision_outcome || 'pending'} •
                      Reason: {decision.reason_code || decision.decision_reason_code || decision.entry_reason_code || 'n/a'}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Decision detail view */}
        <div className="decision-detail">
          {selectedDecision ? (
            <Card className="p-6">
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xl font-bold">
                    Decision: <span className={getDecisionColor(selectedDecision.decision)}>
                      {selectedDecision.decision?.toUpperCase()}
                    </span>
                  </h3>
                  <Badge className={getConfidenceColor(selectedDecision.confidence)}>
                    Confidence: {(selectedDecision.confidence * 100).toFixed(1)}%
                  </Badge>
                </div>
                <p className="text-sm text-gray-500">
                  {selectedDecision.symbol} • {new Date(selectedDecision.timestamp).toLocaleString()}
                </p>
              </div>

              {/* Market Data */}
              {selectedDecision.market_data && (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">Market Data</h4>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>Price: ${selectedDecision.market_data.price?.toLocaleString()}</div>
                    <div>Volume: ${selectedDecision.market_data.volume?.toLocaleString()}</div>
                    <div>Change 24h: {selectedDecision.market_data.change_24h?.toFixed(2)}%</div>
                    <div>Volatility: {selectedDecision.market_data.volatility?.toFixed(2)}%</div>
                  </div>
                </div>
              )}

              {/* Regime State */}
              {selectedDecision.regime_state && (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">Market Regime</h4>
                  <div className="text-sm">
                    <Badge variant="outline">
                      {selectedDecision.regime_state.regime?.toUpperCase().replace('_', ' ')}
                    </Badge>
                    <span className="ml-2">
                      Confidence: {(selectedDecision.regime_state.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              )}

              {/* Component Signals */}
              {selectedDecision.component_scores && (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">Signal Components</h4>
                  <div className="space-y-2">
                    {Object.entries(selectedDecision.component_scores).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between text-sm">
                        <span className="capitalize">{key.replace('_', ' ')}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-32 h-2 bg-gray-200 rounded">
                            <div
                              className={`h-full rounded ${value > 0 ? 'bg-green-500' : 'bg-red-500'}`}
                              style={{ width: `${Math.abs(value) * 100}%` }}
                            />
                          </div>
                          <span className={value > 0 ? 'text-green-600' : 'text-red-600'}>
                            {(value * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Reasoning */}
              {selectedDecision.reasoning && selectedDecision.reasoning.length > 0 && (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">AI Reasoning</h4>
                  <ul className="space-y-1 text-sm">
                    {selectedDecision.reasoning.map((reason, idx) => (
                      <li key={idx} className="flex items-start">
                        <span className="mr-2">•</span>
                        <span>{reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Position Sizing */}
              {selectedDecision.position_size_multiplier && (
                <div className="mb-4">
                  <h4 className="font-semibold mb-2">Position Sizing</h4>
                  <div className="text-sm">
                    Multiplier: <strong>{selectedDecision.position_size_multiplier.toFixed(2)}x</strong>
                    {selectedDecision.stop_loss && (
                      <span className="ml-4">Stop Loss: ${selectedDecision.stop_loss.toLocaleString()}</span>
                    )}
                    {selectedDecision.take_profit && (
                      <span className="ml-4">Take Profit: ${selectedDecision.take_profit.toLocaleString()}</span>
                    )}
                  </div>
                </div>
              )}
            </Card>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <div className="text-center">
                <p className="text-lg mb-2">No decision selected</p>
                <p className="text-sm">Click on a decision in the timeline or press play</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
