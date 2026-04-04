import React, { useState } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { getAllExchanges } from '../../../config/exchanges';
import CurrencyConverter from '../../../components/CurrencyConverter';

// ── Bulk Create helpers ────────────────────────────────────────────────────

function BulkRiskRow({ label, value, onChange, min = 0, max }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
      <label style={{ minWidth: '120px', fontSize: '0.85rem', color: 'var(--muted)' }}>{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={e => onChange(Math.max(min, Math.min(max, parseInt(e.target.value) || 0)))}
        style={{ width: '64px', padding: '5px 8px', borderRadius: '6px', border: '1px solid var(--line)',
          background: 'rgba(255,255,255,0.06)', color: 'var(--text)', textAlign: 'center' }}
      />
    </div>
  );
}

function BulkCreateForm({ botType, handleBulkCreateBots }) {
  const isScalper = botType === 'scalper';
  const [exchange, setExchange] = useState('luno');
  const [capitalPerBot, setCapitalPerBot] = useState(1000);
  const [safeCount, setSafeCount] = useState(3);
  const [balancedCount, setBalancedCount] = useState(2);
  const [aggressiveCount, setAggressiveCount] = useState(1);
  const [profitRouting, setProfitRouting] = useState('RETURN_TO_MAIN');

  const total = safeCount + balancedCount + aggressiveCount;
  const totalCapital = total * capitalPerBot;
  const isValid = total >= 1 && total <= 30 && capitalPerBot >= 1000;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!handleBulkCreateBots) return;
    handleBulkCreateBots({
      bot_type: botType,
      exchange,
      count: total,
      capital_per_bot: capitalPerBot,
      safe_count: safeCount,
      risky_count: balancedCount,
      aggressive_count: aggressiveCount,
      profit_routing: profitRouting,
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '14px',
        marginBottom: '18px',
      }}>
        {/* Exchange */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem' }}>
            Exchange Platform
          </label>
          <select
            value={exchange}
            onChange={e => setExchange(e.target.value)}
            style={{ width: '100%' }}
          >
            {getAllExchanges().map(ex => (
              <option key={ex.id} value={ex.id} disabled={ex.comingSoon}>
                {ex.icon} {ex.displayName}
              </option>
            ))}
          </select>
        </div>

        {/* Capital per bot */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem' }}>
            Capital per Bot (ZAR, min R1,000)
          </label>
          <input
            type="number"
            min="1000"
            step="100"
            value={capitalPerBot}
            onChange={e => setCapitalPerBot(Math.max(1000, parseInt(e.target.value) || 1000))}
            required
            style={{ width: '100%' }}
          />
        </div>

        {/* Profit routing (scalper only) */}
        {isScalper && (
          <div>
            <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem' }}>
              Profit Routing
            </label>
            <select
              value={profitRouting}
              onChange={e => setProfitRouting(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="RETURN_TO_MAIN">Return to Main — profits → main capital</option>
              <option value="SCALPER_GROWTH">Scalper Growth — profits reinvested in scalpers</option>
            </select>
          </div>
        )}
      </div>

      {/* Risk distribution */}
      <div style={{
        background: 'rgba(255,255,255,0.04)',
        borderRadius: '10px',
        padding: '14px 18px',
        marginBottom: '16px',
        border: '1px solid rgba(255,255,255,0.07)',
      }}>
        <div style={{ fontSize: '0.88rem', fontWeight: 600, marginBottom: '10px', color: 'var(--text)' }}>
          Risk Distribution
        </div>
        <BulkRiskRow label="🛡️ Safe" value={safeCount} onChange={setSafeCount} max={30} />
        <BulkRiskRow label="⚖️ Balanced" value={balancedCount} onChange={setBalancedCount} max={30} />
        <BulkRiskRow label="🚀 Aggressive" value={aggressiveCount} onChange={setAggressiveCount} max={30} />
        <div style={{
          marginTop: '10px',
          paddingTop: '10px',
          borderTop: '1px solid rgba(255,255,255,0.07)',
          fontSize: '0.85rem',
          color: total > 30 ? 'var(--danger)' : 'var(--success)',
        }}>
          Total: <strong>{total}</strong> bot{total !== 1 ? 's' : ''}
          {total > 30 && ' — max 30'}
        </div>
      </div>

      {/* Capital preview */}
      <div style={{
        background: 'rgba(74,144,226,0.1)',
        border: '1px solid rgba(74,144,226,0.25)',
        borderRadius: '8px',
        padding: '12px 16px',
        marginBottom: '16px',
        fontSize: '0.85rem',
        color: 'var(--text)',
      }}>
        💰 <strong>R{capitalPerBot.toLocaleString()}</strong> × {total} bots =&nbsp;
        <strong style={{ color: 'var(--success)' }}>R{totalCapital.toLocaleString()}</strong> total capital
        &nbsp;·&nbsp; All bots start in <strong>PAPER mode</strong>
      </div>

      <button type="submit" disabled={!isValid} style={{ opacity: isValid ? 1 : 0.5 }}>
        📦 Create {total} {isScalper ? 'Scalper' : ''} Bot{total !== 1 ? 's' : ''} on {exchange.charAt(0).toUpperCase() + exchange.slice(1)}
      </button>
    </form>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function BotManagementSection({
  axiosConfig, // kept for forward-compat
  botManagementTab,
  handleBulkCreateBots,
  handleCreateBot,
  handleCreateScalperBot,
  handleCreateUAgent,
  setBotManagementTab,
  embedded = false,
}) {
  const content = (
    <>
    <div className="card">
      {!embedded && (
        <SectionHeader
          title="🤖 Bot Management"
          subtitle="Create and configure trading bots. Use Bot Fleet to monitor and control them."
        />
      )}
        <div className="bot-tabs">
          <button
            className={`bot-tab ${botManagementTab === 'creation' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('creation')}
          >
            🤖 Bot Creator
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'scalper' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('scalper')}
          >
            ⚡ Scalper Bot Creator
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'bulk' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('bulk')}
          >
            📦 Bulk Create
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'uagent' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('uagent')}
          >
            🌐 Fetch.ai / uAgents
          </button>
        </div>

        {/* ── Tab 1: Bot Creator ─────────────────────────────── */}
        {botManagementTab === 'creation' && (
          <div>
            <div className="bot-form-card">
              <h3>🤖 Bot Creator</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px' }}>
                Standard trading bot with a 7-day learning period. Starts in paper mode automatically.
              </p>
              <form onSubmit={handleCreateBot}>
                <div className="bot-form-grid">
                  <div>
                    <label htmlFor="bot-name">Bot Name</label>
                    <input id="bot-name" name="bot-name" placeholder="My Trading Bot" type="text" required />
                  </div>
                  <div>
                    <label htmlFor="bot-budget">Budget (Min R1000)</label>
                    <input
                      id="bot-budget"
                      name="bot-budget"
                      type="number"
                      min="1000"
                      step="100"
                      defaultValue="1000"
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="bot-exchange">Exchange Platform</label>
                    <select id="bot-exchange" name="bot-exchange" defaultValue="luno">
                      {getAllExchanges().map(exchange => (
                        <option key={exchange.id} value={exchange.id} disabled={exchange.comingSoon}>
                          {exchange.icon} {exchange.displayName}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="bot-risk">Risk Mode</label>
                    <select id="bot-risk" name="bot-risk">
                      <option value="safe">Safe</option>
                      <option value="balanced">Balanced</option>
                      <option value="aggressive">Aggressive</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="bot-strategy">Strategy Preset</label>
                    <select id="bot-strategy" name="bot-strategy" defaultValue="adaptive">
                      <option value="adaptive">Adaptive Core</option>
                      <option value="trend">Trend Follow</option>
                      <option value="mean_reversion">Mean Reversion</option>
                      <option value="scalping">Scalping</option>
                    </select>
                  </div>
                  {/* Hidden field ensures bot_type is always sent as 'normal' */}
                  <input type="hidden" name="bot-type" value="normal" />
                  <div>
                    <button type="submit">Create Bot (7 Day Learning)</button>
                  </div>
                </div>
              </form>
            </div>
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '12px' }}>
              💡 To monitor and control your bots, go to <strong>Bot Fleet</strong> in the sidebar.
            </p>
          </div>
        )}

        {/* ── Tab 2: Scalper Bot Creator ─────────────────────── */}
        {botManagementTab === 'scalper' && (
          <div>
            <div className="bot-form-card">
              <h3>⚡ Scalper Bot Creator</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px' }}>
                High-frequency scalper bot optimized for short-duration trades. Starts in paper mode. Minimum capital R1000 (or equivalent in exchange quote currency).
              </p>
              <form onSubmit={handleCreateScalperBot}>
                <div className="bot-form-grid">
                  <div>
                    <label htmlFor="scalper-name">Bot Name</label>
                    <input id="scalper-name" name="scalper-name" placeholder="My Scalper Bot" type="text" required />
                  </div>
                  <div>
                    <label htmlFor="scalper-budget">Capital Allocation (Min R1000)</label>
                    <input
                      id="scalper-budget"
                      name="scalper-budget"
                      type="number"
                      min="1000"
                      step="100"
                      defaultValue="1000"
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="scalper-exchange">Exchange Platform</label>
                    <select id="scalper-exchange" name="scalper-exchange" defaultValue="luno">
                      {getAllExchanges().map(exchange => (
                        <option key={exchange.id} value={exchange.id} disabled={exchange.comingSoon}>
                          {exchange.icon} {exchange.displayName}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="scalper-risk">Risk Profile</label>
                    <select id="scalper-risk" name="scalper-risk" defaultValue="balanced">
                      <option value="safe">Conservative — tighter spreads, slower entries</option>
                      <option value="balanced">Balanced — standard scalper thresholds</option>
                      <option value="aggressive">Aggressive — wider EV range, faster execution</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="scalper-routing">Profit Routing</label>
                    <select id="scalper-routing" name="scalper-routing" defaultValue="RETURN_TO_MAIN">
                      <option value="RETURN_TO_MAIN">Return to Main — profits go back to main capital</option>
                      <option value="SCALPER_GROWTH">Scalper Growth — profits reinvested in scalper pool</option>
                    </select>
                  </div>
                  {/* Hidden field ensures bot_type is always sent as 'scalper' */}
                  <input type="hidden" name="bot-type" value="scalper" />
                  <div>
                    <button type="submit">Deploy Scalper Bot</button>
                  </div>
                </div>
              </form>
            </div>
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '12px' }}>
              💡 Scalper bots appear in <strong>Bot Fleet → Scalper Bots</strong> after creation.
            </p>
          </div>
        )}

        {/* ── Tab 3: Bulk Create ─────────────────────────────── */}
        {botManagementTab === 'bulk' && (
          <div>
            <div className="bot-form-card">
              <h3>📦 Bulk Bot Creator</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '16px' }}>
                Create multiple bots at once on any exchange. Set the risk distribution and capital per bot —
                the system creates all bots in one click. All bots start in <strong>Paper Mode</strong>.
              </p>

              <BulkTypeToggle handleBulkCreateBots={handleBulkCreateBots} />
            </div>
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '12px' }}>
              💡 Created bots appear in <strong>Bot Fleet</strong>. Each bot gets its own paper wallet allocation.
            </p>
          </div>
        )}

        {/* ── Tab 4: Fetch.ai / uAgents ─────────────────────── */}
        {botManagementTab === 'uagent' && (
          <div>
            <div className="bot-form-card">
              <h3>🌐 Fetch.ai / uAgents</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px' }}>
                Deploy a Fetch.ai autonomous agent. Upload your agent script and configure its strategy.
              </p>
              <form onSubmit={handleCreateUAgent}>
                <div className="bot-form-grid">
                  <div>
                    <label htmlFor="uagent-name">uAgent Name</label>
                    <input id="uagent-name" name="uagent-name" placeholder="Custom Agent" type="text" required />
                  </div>
                  <div>
                    <label htmlFor="uagent-strategy">Strategy</label>
                    <select id="uagent-strategy" name="uagent-strategy" defaultValue="adaptive">
                      <option value="adaptive">Adaptive</option>
                      <option value="trend">Trend</option>
                      <option value="mean_reversion">Mean Reversion</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="uagent-file">Upload Agent Script (.py)</label>
                    <input id="uagent-file" name="uagent-file" type="file" accept=".py" required />
                  </div>
                  {/* Hidden field ensures bot_type is always sent as 'uagent' */}
                  <input type="hidden" name="bot-type" value="uagent" />
                  <div>
                    <button type="submit">Deploy uAgent</button>
                  </div>
                </div>
              </form>
            </div>
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '12px' }}>
              💡 Deployed uAgents appear in the <strong>uAgents</strong> tab of <strong>Bot Fleet</strong>.
            </p>
          </div>
        )}
      </div>
      {/* Currency converter — informational only; helps users enter funding amounts correctly */}
      <div className="card" style={{ marginTop: '16px' }}>
        <SectionHeader
          title="💱 Currency Converter"
          subtitle="Convert ZAR ↔ USDT and other currencies before funding a bot."
        />
        <CurrencyConverter />
      </div>
    </>
  );

  if (embedded) return content;
  return <section className="section active">{content}</section>;
}

/**
 * BulkTypeToggle — internal component that owns the normal/scalper sub-tab state
 * so we avoid placing useState calls inside the mapping above.
 */
function BulkTypeToggle({ handleBulkCreateBots }) {
  const [bulkType, setBulkType] = useState('normal');

  const subTabStyle = (active) => ({
    padding: '7px 18px',
    background: active ? 'rgba(74,144,226,0.25)' : 'rgba(255,255,255,0.05)',
    border: `1px solid ${active ? 'rgba(74,144,226,0.6)' : 'rgba(255,255,255,0.1)'}`,
    borderRadius: '8px',
    color: active ? '#fff' : 'var(--muted)',
    cursor: 'pointer',
    fontSize: '0.88rem',
    fontWeight: active ? 700 : 500,
    transition: 'all 0.2s',
  });

  return (
    <>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button type="button" onClick={() => setBulkType('normal')} style={subTabStyle(bulkType === 'normal')}>
          🤖 Normal Bots
        </button>
        <button type="button" onClick={() => setBulkType('scalper')} style={subTabStyle(bulkType === 'scalper')}>
          ⚡ Scalper Bots
        </button>
      </div>
      <BulkCreateForm botType={bulkType} handleBulkCreateBots={handleBulkCreateBots} />
    </>
  );
}
