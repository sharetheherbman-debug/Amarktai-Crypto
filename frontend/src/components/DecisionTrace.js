import { useState, useEffect, useRef, useMemo } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import './DecisionTrace.css';

/**
 * DecisionTrace Component
 *
 * Operator-grade decision & trade trace UI.
 * Left panel: timeline of recent decisions (DVR playback).
 * Right panel: full operator hierarchy — bot / exchange / pair / price / P&L /
 *   fees / slippage / TP–SL / pairs evaluated / expectancy / regime / strategy.
 *
 * Data sources:
 *   - /api/advanced/decisions/recent  — decision timeline
 *   - /api/trades/recent             — enriched trade details (decision_trace)
 */
export default function DecisionTrace() {
  const [decisions, setDecisions]               = useState([]);
  const [bots, setBots]                         = useState([]);
  const [recentTrades, setRecentTrades]         = useState([]);
  const [selectedBotId, setSelectedBotId]       = useState('all');
  const [selectedDecision, setSelectedDecision] = useState(null);
  const [selectedTrade, setSelectedTrade]       = useState(null);
  const [isPlaying, setIsPlaying]               = useState(false);
  const [currentIndex, setCurrentIndex]         = useState(0);
  const [filter, setFilter]                     = useState('all');
  const [loading, setLoading]                   = useState(true);
  const playbackIntervalRef = useRef(null);
  const lastUpdate = useLastUpdate('decisions');

  useEffect(() => {
    loadBots();
    loadInitialDecisions();
    loadRecentTrades();
  }, []);

  useEffect(() => {
    loadInitialDecisions();
  }, [selectedBotId]);

  const loadBots = async () => {
    try {
      const data = await get('/bots/status');
      setBots(Array.isArray(data?.bots) ? data.bots : []);
    } catch (e) {
      console.error('Failed to load bots:', e);
    }
  };

  const loadInitialDecisions = async () => {
    try {
      const botFilter = selectedBotId && selectedBotId !== 'all'
        ? `&bot_id=${encodeURIComponent(selectedBotId)}` : '';
      const data = await get(`/advanced/decisions/recent?limit=50${botFilter}`);
      const list = data.decisions || [];
      setDecisions(list);
      setSelectedDecision(list[0] || null);
      setCurrentIndex(0);
      setLoading(false);
    } catch (e) {
      console.error('Failed to load decisions:', e);
      setLoading(false);
    }
  };

  const loadRecentTrades = async () => {
    try {
      const data = await get('/trades/recent?limit=100');
      setRecentTrades(Array.isArray(data?.trades) ? data.trades : []);
    } catch (e) {
      console.error('Failed to load recent trades:', e);
    }
  };

  // Enrich selected decision with matching trade when a decision is clicked
  useEffect(() => {
    if (!selectedDecision) { setSelectedTrade(null); return; }
    const bid = selectedDecision.bot_id;
    const ts  = selectedDecision.timestamp;
    if (!bid || !ts) { setSelectedTrade(null); return; }
    // Find the closest trade for this bot around the same timestamp (±60s)
    const decTime = new Date(ts).getTime();
    const match = recentTrades.find(t => {
      if (t.bot_id !== bid) return false;
      const tTime = new Date(t.timestamp || t.created_at || 0).getTime();
      return Math.abs(tTime - decTime) < 60000;
    });
    setSelectedTrade(match || null);
  }, [selectedDecision, recentTrades]);

  // Subscribe to real-time decision updates
  useRealtimeEvent('decisions', (decision) => {
    setDecisions(prev => [decision, ...prev].slice(0, 100));
  }, []);

  const filteredDecisions = useMemo(() => {
    return decisions.filter(d => {
      if (filter === 'all') return true;
      return d.decision?.toLowerCase() === filter;
    });
  }, [decisions, filter]);

  // DVR playback
  useEffect(() => {
    if (isPlaying && filteredDecisions.length > 0) {
      playbackIntervalRef.current = setInterval(() => {
        setCurrentIndex(prev => {
          const next = prev + 1;
          if (next >= filteredDecisions.length) { setIsPlaying(false); return prev; }
          setSelectedDecision(filteredDecisions[next]);
          return next;
        });
      }, 2000);
    } else if (playbackIntervalRef.current) {
      clearInterval(playbackIntervalRef.current);
      playbackIntervalRef.current = null;
    }
    return () => { if (playbackIntervalRef.current) clearInterval(playbackIntervalRef.current); };
  }, [isPlaying, filteredDecisions]);

  const handlePlayPause  = () => setIsPlaying(!isPlaying);
  const handleStop       = () => { setIsPlaying(false); setCurrentIndex(0); setSelectedDecision(filteredDecisions[0] || null); };
  const handleStepForward  = () => { if (currentIndex < filteredDecisions.length - 1) { const n = currentIndex + 1; setCurrentIndex(n); setSelectedDecision(filteredDecisions[n]); } };
  const handleStepBackward = () => { if (currentIndex > 0) { const p = currentIndex - 1; setCurrentIndex(p); setSelectedDecision(filteredDecisions[p]); } };
  const handleDecisionClick = (decision, idx) => { setSelectedDecision(decision); setCurrentIndex(idx); setIsPlaying(false); };

  const decisionColor = (d) => {
    const v = d?.toLowerCase() || '';
    if (v.includes('buy'))  return 'text-green-400';
    if (v.includes('sell')) return 'text-red-400';
    return 'text-gray-400';
  };

  const confidenceBadge = (c) => {
    if (c >= 0.7) return 'bg-green-900 text-green-300 border-green-700';
    if (c >= 0.45) return 'bg-yellow-900 text-yellow-300 border-yellow-700';
    return 'bg-red-900 text-red-300 border-red-700';
  };

  const pnlColor = (v) => (v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-400');

  const fmt = (v, d = 2) => (v != null && !isNaN(Number(v)) ? Number(v).toFixed(d) : '—');
  const fmtPct = (v, d = 2) => (v != null && !isNaN(Number(v)) ? `${Number(v).toFixed(d)}%` : '—');
  const fmtZar = (v, d = 2) => (v != null && !isNaN(Number(v)) ? `R ${Number(v).toFixed(d)}` : '—');

  // Merge decision + trade fields for display
  const d = selectedDecision || {};
  const t = selectedTrade || {};
  const dt = t.decision_trace || d.decision_trace || {};

  const displayEntry    = t.entry_price  || d.entry_price;
  const displayAmount   = t.amount       || d.amount;
  const displayNotional = t.trade_amount || t.entry_value || d.trade_amount;
  const displayPnl      = t.profit_loss  || t.net_profit  || d.profit_loss;
  const displayFees     = t.fees_total   || t.fees        || d.fees;
  const displaySlipBps  = t.slippage_bps || (t.slippage_rate != null ? (t.slippage_rate * 10000) : null);
  const displaySL       = t.stop_loss_price  || d.stop_loss;
  const displayTP       = t.take_profit_price|| d.take_profit;
  const displaySLPct    = t.stop_loss_pct    || d.stop_loss_pct;
  const displayTPPct    = t.take_profit_pct  || d.take_profit_pct;
  const displayRegime   = dt.regime  || d.regime || d.market_regime || d.ai_regime || t.ai_regime;
  const displayPlaybook = dt.playbook|| d.playbook|| d.strategy;
  const displayExpect   = dt.expectancy_estimate != null ? dt.expectancy_estimate : d.expectancy_net_edge_pct;
  const displayCost     = dt.cost_estimate != null ? dt.cost_estimate : d.estimated_cost_pct;
  const displayPairsN   = dt.evaluated_pairs_count || d.evaluated_pairs_count;
  const displayChosen   = dt.chosen_pair || d.symbol || t.symbol;
  const displayTopCands = dt.top_candidates || [];
  const displaySide     = t.trade_type || d.decision || 'BUY';
  const displayExchange = t.exchange || d.exchange;
  const displayBotName  = d.bot_name || t.bot_name;
  const displayStatus   = t.status   || d.status;
  const displayHoldSec  = dt.planned_exit?.hard_max_hold_seconds;
  const displayHoldMin  = dt.planned_exit?.time_exit_minutes;
  const displayConf     = d.confidence ?? d.ai_confidence ?? t.ai_confidence;

  return (
    <div className="decision-trace-container">
      {/* ── Header ── */}
      <div className="decision-trace-header">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold">Decision Trace</h2>
            <p className="text-sm" style={{ color: 'var(--muted, #8899aa)' }}>Operator Trade &amp; Decision Provenance</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={lastUpdate ? 'default' : 'destructive'}>
              {lastUpdate ? '🟢 Live' : '🔴 Waiting'}
            </Badge>
            {lastUpdate && (
              <span className="text-xs" style={{ color: 'var(--muted, #8899aa)' }}>
                {new Date(lastUpdate).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        <div className="dvr-controls">
          <button className="control-btn" onClick={handleStop} title="Stop">⏹</button>
          <button className="control-btn" onClick={handleStepBackward} disabled={currentIndex === 0} title="Previous">⏮</button>
          <button className="control-btn play-pause" onClick={handlePlayPause} title={isPlaying ? 'Pause' : 'Play'}>
            {isPlaying ? '⏸' : '▶'}
          </button>
          <button className="control-btn" onClick={handleStepForward} disabled={currentIndex >= filteredDecisions.length - 1} title="Next">⏭</button>

          <select
            className="filter-select"
            value={selectedBotId}
            onChange={e => setSelectedBotId(e.target.value)}
          >
            <option value="all">All Bots</option>
            {bots.map(b => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>

          <select
            className="filter-select"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          >
            <option value="all">All Decisions</option>
            <option value="buy">Buy Only</option>
            <option value="sell">Sell Only</option>
            <option value="neutral">Neutral Only</option>
          </select>
        </div>

        {filteredDecisions.length > 0 && (
          <div className="progress-container">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${((currentIndex + 1) / filteredDecisions.length) * 100}%` }} />
            </div>
            <span className="progress-text">{currentIndex + 1} / {filteredDecisions.length}</span>
          </div>
        )}
      </div>

      {/* ── Main content ── */}
      <div className="decision-trace-content">
        {/* Timeline sidebar */}
        <div className="timeline-sidebar">
          <h3 className="text-sm font-semibold mb-2">Decision Timeline</h3>
          <div className="timeline-list">
            {filteredDecisions.length === 0 ? (
              <p className="text-sm text-center py-4" style={{ color: 'var(--muted, #8899aa)' }}>
                {loading ? 'Loading…' : 'No decisions yet. Waiting for trades…'}
              </p>
            ) : filteredDecisions.map((dec, idx) => (
              <div
                key={idx}
                className={`timeline-item ${idx === currentIndex ? 'active' : ''}`}
                onClick={() => handleDecisionClick(dec, idx)}
              >
                <div className="timeline-marker" />
                <div className="timeline-content">
                  <div className="flex items-center justify-between">
                    <span className={`font-semibold text-xs ${decisionColor(dec.decision)}`}>
                      {dec.decision?.toUpperCase() || 'SKIP'}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--muted, #8899aa)' }}>
                      {new Date(dec.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--muted2, #667788)' }}>
                    {dec.bot_name || dec.bot_id?.slice(0, 8) || '—'} · {dec.symbol || dec.pair || '—'} · {(dec.exchange || '—').toUpperCase()}
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--muted2, #667788)' }}>
                    Regime: {dec.regime || dec.market_regime || '—'} ·
                    Conf: {dec.confidence != null ? `${(Number(dec.confidence) * 100).toFixed(0)}%` : '—'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Detail panel ── */}
        <div className="decision-detail">
          {selectedDecision ? (
            <div className="dt-panel">

              {/* ─ Row 1: Bot / Exchange / Pair / Timestamp ─ */}
              <div className="dt-section dt-header-row">
                <div className="dt-hierarchy">
                  <span className="dt-label">BOT</span>
                  <span className="dt-value dt-bot-name">{displayBotName || d.bot_id?.slice(0, 10) || '—'}</span>
                  <span className="dt-sep">›</span>
                  <span className="dt-label">EXCHANGE</span>
                  <span className="dt-value">{(displayExchange || '—').toUpperCase()}</span>
                  <span className="dt-sep">›</span>
                  <span className="dt-label">PAIR</span>
                  <span className="dt-value dt-pair">{displayChosen || '—'}</span>
                </div>
                <div className="dt-meta-right">
                  <span className="dt-timestamp">{d.timestamp ? new Date(d.timestamp).toLocaleString() : '—'}</span>
                  {displayStatus && (
                    <span className={`dt-status-badge dt-status-${(displayStatus || '').toLowerCase()}`}>
                      {displayStatus.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>

              {/* ─ Row 2: Side / Entry / Size / Notional ─ */}
              <div className="dt-section dt-grid-4">
                <div className="dt-cell">
                  <span className="dt-cell-label">SIDE</span>
                  <span className={`dt-cell-value dt-side ${decisionColor(displaySide)}`}>
                    {(displaySide || '—').toUpperCase()}
                  </span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">ENTRY PRICE</span>
                  <span className="dt-cell-value">{displayEntry != null ? fmtZar(displayEntry, 4) : '—'}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">SIZE (BASE)</span>
                  <span className="dt-cell-value">{fmt(displayAmount, 6)}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">NOTIONAL</span>
                  <span className="dt-cell-value">{fmtZar(displayNotional)}</span>
                </div>
              </div>

              {/* ─ Row 3: P&L / Fees / Slippage / Confidence ─ */}
              <div className="dt-section dt-grid-4">
                <div className="dt-cell">
                  <span className="dt-cell-label">REALISED P&amp;L</span>
                  <span className={`dt-cell-value ${pnlColor(displayPnl)}`}>
                    {displayPnl != null ? fmtZar(displayPnl) : (displayStatus === 'open' ? '⏳ open' : '—')}
                  </span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">FEES PAID</span>
                  <span className="dt-cell-value dt-muted">{fmtZar(displayFees)}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">SLIPPAGE</span>
                  <span className="dt-cell-value dt-muted">{displaySlipBps != null ? `${fmt(displaySlipBps, 1)} bps` : '—'}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">CONFIDENCE</span>
                  <span className={`dt-cell-value dt-badge ${confidenceBadge(displayConf)}`}>
                    {displayConf != null ? fmtPct(displayConf * 100, 1) : '—'}
                  </span>
                </div>
              </div>

              {/* ─ Row 4: Expectancy / Cost / Pairs evaluated / Chosen ─ */}
              <div className="dt-section dt-grid-4">
                <div className="dt-cell">
                  <span className="dt-cell-label">EXPECTANCY</span>
                  <span className={`dt-cell-value ${pnlColor(displayExpect)}`}>
                    {displayExpect != null ? fmtZar(displayExpect, 4) : '—'}
                  </span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">EST. COST</span>
                  <span className="dt-cell-value dt-muted">{fmtPct(displayCost)}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">PAIRS EVAL.</span>
                  <span className="dt-cell-value">{displayPairsN != null ? displayPairsN : '—'}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">CHOSEN PAIR</span>
                  <span className="dt-cell-value dt-pair">{displayChosen || '—'}</span>
                </div>
              </div>

              {/* ─ Row 5: Regime / Strategy / TP / SL ─ */}
              <div className="dt-section dt-grid-4">
                <div className="dt-cell">
                  <span className="dt-cell-label">REGIME</span>
                  <span className="dt-cell-value dt-regime">{(displayRegime || '—').toUpperCase().replace(/_/g, ' ')}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">STRATEGY</span>
                  <span className="dt-cell-value">{(displayPlaybook || '—').toUpperCase()}</span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">TAKE PROFIT</span>
                  <span className="dt-cell-value text-green-400">
                    {displayTP != null ? fmtZar(displayTP, 4) : '—'}
                    {displayTPPct != null && <span className="dt-sub"> ({fmtPct(displayTPPct * 100, 1)})</span>}
                  </span>
                </div>
                <div className="dt-cell">
                  <span className="dt-cell-label">STOP LOSS</span>
                  <span className="dt-cell-value text-red-400">
                    {displaySL != null ? fmtZar(displaySL, 4) : '—'}
                    {displaySLPct != null && <span className="dt-sub"> ({fmtPct(displaySLPct * 100, 1)})</span>}
                  </span>
                </div>
              </div>

              {/* ─ Row 6: Hold windows ─ */}
              {(displayHoldMin || displayHoldSec) && (
                <div className="dt-section dt-grid-4">
                  <div className="dt-cell">
                    <span className="dt-cell-label">SOFT EXIT</span>
                    <span className="dt-cell-value dt-muted">{displayHoldMin != null ? `${displayHoldMin} min` : '—'}</span>
                  </div>
                  <div className="dt-cell">
                    <span className="dt-cell-label">HARD EXIT</span>
                    <span className="dt-cell-value dt-muted">{displayHoldSec != null ? `${Math.round(displayHoldSec / 60)} min` : '—'}</span>
                  </div>
                  <div className="dt-cell dt-cell-span2">
                    <span className="dt-cell-label">EXIT REASON</span>
                    <span className="dt-cell-value dt-muted">
                      {t.trade_close_reason || dt.planned_exit?.next_exit_reason || '—'}
                    </span>
                  </div>
                </div>
              )}

              {/* ─ Top candidates ─ */}
              {displayTopCands.length > 0 && (
                <div className="dt-section">
                  <div className="dt-section-title">TOP PAIR CANDIDATES</div>
                  <div className="dt-candidates">
                    {displayTopCands.slice(0, 5).map((c, i) => (
                      <div key={i} className="dt-candidate-row">
                        <span className="dt-cand-rank">#{i + 1}</span>
                        <span className="dt-cand-pair">{c.symbol || c.pair || '—'}</span>
                        <span className="dt-cand-score dt-muted">score: {fmt(c.score, 3)}</span>
                        {c.regime && <span className="dt-cand-regime">{c.regime}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ─ Raw signals fallback ─ */}
              {d.component_scores && (
                <div className="dt-section">
                  <div className="dt-section-title">SIGNAL COMPONENTS</div>
                  <div className="dt-signals">
                    {Object.entries(d.component_scores).map(([k, v]) => (
                      <div key={k} className="dt-signal-row">
                        <span className="dt-signal-name">{k.replace(/_/g, ' ')}</span>
                        <div className="dt-signal-bar-bg">
                          <div
                            className={`dt-signal-bar ${Number(v) > 0 ? 'dt-bar-pos' : 'dt-bar-neg'}`}
                            style={{ width: `${Math.min(100, Math.abs(Number(v) || 0) * 100)}%` }}
                          />
                        </div>
                        <span className={`dt-signal-val ${Number(v) > 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {fmtPct(Number(v) * 100, 1)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ─ AI reasoning ─ */}
              {d.reasoning && d.reasoning.length > 0 && (
                <div className="dt-section">
                  <div className="dt-section-title">AI REASONING</div>
                  <ul className="dt-reasoning">
                    {d.reasoning.map((r, i) => (
                      <li key={i}><span className="dt-bullet">›</span>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

            </div>
          ) : (
            <div className="dt-empty">
              <p className="dt-empty-title">No decision selected</p>
              <p className="dt-empty-sub">Click a row in the timeline or press ▶ to replay</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
