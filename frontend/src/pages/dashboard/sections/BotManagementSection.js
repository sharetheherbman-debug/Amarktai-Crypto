import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { getAllExchanges } from '../../../config/exchanges';
import CurrencyConverter from '../../../components/CurrencyConverter';

export default function BotManagementSection({
  axiosConfig, // kept for forward-compat
  botManagementTab,
  handleCreateBot,
  handleCreateScalperBot,
  handleCreateUAgent,
  setBotManagementTab,
  embedded = false,
}) {
  const content = (
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

        {/* ── Tab 3: Fetch.ai / uAgents ─────────────────────── */}
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
  );

  if (embedded) return content;
  return <section className="section active">{content}</section>;
}
