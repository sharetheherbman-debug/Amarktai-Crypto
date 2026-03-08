import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import ScalperBotsPanel from './ScalperBotsPanel';
import { getAllExchanges } from '../../../config/exchanges';

export default function BotManagementSection({
  axiosConfig,
  botManagementTab,
  handleCreateBot,
  handleCreateUAgent,
  setBotManagementTab,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 Bot Management"
          subtitle="Create and deploy trading bots. Use Bot Fleet to monitor and control them."
        />
        <div className="bot-tabs">
          <button
            className={`bot-tab ${botManagementTab === 'creation' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('creation')}
          >
            🤖 Normal Bot Creator
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

        {botManagementTab === 'scalper' && (
          <ScalperBotsPanel axiosConfig={axiosConfig || { headers: {} }} />
        )}

        {botManagementTab === 'creation' && (
          <div>
            <div className="bot-form-card">
              <h3>🤖 Normal Bot Creator</h3>
              <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px'}}>
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
                        <option
                          key={exchange.id}
                          value={exchange.id}
                          disabled={exchange.comingSoon}
                        >
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
              To create a ⚡ Scalper Bot, use the <strong>Scalper Bots</strong> tab above.
            </p>
          </div>
        )}

        {botManagementTab === 'uagent' && (
          <div>
            <div className="bot-form-card">
              <h3>🌐 Fetch.ai / uAgents Creator</h3>
              <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px'}}>
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
    </section>
  );
}
