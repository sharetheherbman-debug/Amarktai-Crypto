import React, { useEffect, useState } from 'react';
import { get } from '../../../lib/apiClient';
import realtimeClient from '../../../lib/realtime';

export default function AiChatSection({
  chatMessages, chatEndRef, chatInput, setChatInput, chatSending, awaitingPassword,
  handleChatKeyDown, handleSendMessage, loadChatHistory, handleClearChatHistory,
  showAITools, setShowAITools, aiTaskLoading,
  handleTriggerLearning, handleEvolveBots, handleGetInsights, handlePredictPrice, handleReinvestProfits,
  hideInlineTools = false,
}) {
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [aiCapabilities, setAiCapabilities] = useState(null);

  const loadCapabilityStatus = async () => {
    try {
      const data = await get('/ai/capability-status');
      setAiCapabilities(data);
    } catch (err) {
      setAiCapabilities({
        degraded_mode: true,
        degraded_features: ['chatops', 'predict_price'],
        capabilities: {
          chatops: { available: false, degraded_reason: 'Capability status unavailable' },
          predict_price: { available: false, degraded_reason: 'Capability status unavailable' },
        }
      });
    }
  };

  useEffect(() => {
    loadCapabilityStatus();
    const unsubscribeSaved = realtimeClient.on('key_saved', loadCapabilityStatus);
    const unsubscribeTested = realtimeClient.on('key_tested', loadCapabilityStatus);
    const unsubscribeDeleted = realtimeClient.on('key_deleted', loadCapabilityStatus);
    const unsubscribeUpdate = realtimeClient.on('api_key_update', loadCapabilityStatus);
    return () => {
      unsubscribeSaved();
      unsubscribeTested();
      unsubscribeDeleted();
      unsubscribeUpdate();
    };
  }, []);

  const capability = aiCapabilities?.capabilities || {};
  const toolDisabledReason = {
    learning: capability.learning?.degraded_reason,
    evolve: capability.bot_evolution?.degraded_reason,
    insights: capability.insights?.degraded_reason,
    predict: capability.predict_price?.degraded_reason,
    reinvest: capability.reinvest_profits?.degraded_reason,
  };

  const isToolBlocked = {
    learning: capability.learning?.available === false,
    evolve: capability.bot_evolution?.available === false,
    insights: capability.insights?.available === false,
    predict: capability.predict_price?.available === false,
    reinvest: capability.reinvest_profits?.available === false,
  };

  return (
    <div className="amk-chat">
      <div className="amk-chat-toolbar">
        <div className="amk-chat-actions">
          <button
            onClick={loadChatHistory}
            style={{
              padding: '6px 12px',
              fontSize: '0.8rem',
              background: 'rgba(56, 189, 248, 0.2)',
              color: 'var(--text)',
              border: '1px solid rgba(56, 189, 248, 0.4)',
              borderRadius: '999px',
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
              background: 'rgba(239, 68, 68, 0.2)',
              color: 'var(--text)',
              border: '1px solid rgba(239, 68, 68, 0.45)',
              borderRadius: '999px',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            🗑️ Clear History
          </button>
          {/* AI Tools / Analytics toggles are hidden when the parent component
              already provides dedicated tabs for these (e.g. WelcomeSection). */}
          {!hideInlineTools && setShowAITools && (
            <button
              onClick={() => setShowAITools(!showAITools)}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                background: showAITools ? 'rgba(56, 189, 248, 0.5)' : 'rgba(56, 189, 248, 0.15)',
                color: 'var(--text)',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                borderRadius: '999px',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              🧠 AI Tools {showAITools ? '▼' : '▶'}
            </button>
          )}
          {!hideInlineTools && (
            <button
              onClick={() => setShowAnalytics(!showAnalytics)}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                background: showAnalytics ? 'rgba(34, 197, 94, 0.4)' : 'rgba(34, 197, 94, 0.15)',
                color: 'var(--text)',
                border: '1px solid rgba(34, 197, 94, 0.4)',
                borderRadius: '999px',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              📊 Analytics {showAnalytics ? '▼' : '▶'}
            </button>
          )}
        </div>
        <div className={`amk-chat-indicator ${chatSending ? 'active' : ''}`}>
          {chatSending ? 'Sending...' : (aiCapabilities?.degraded_mode ? 'Degraded' : 'Ready')}
        </div>
        <img src="/assets/ai/ai-wave.svg" alt="" className="amk-chat-banner" />
      </div>
      {aiCapabilities?.degraded_mode && (
        <div style={{
          marginTop: '8px',
          marginBottom: '8px',
          padding: '8px 10px',
          borderRadius: '8px',
          border: '1px solid rgba(245, 158, 11, 0.45)',
          background: 'rgba(245, 158, 11, 0.14)',
          color: '#f59e0b',
          fontSize: '0.78rem',
          fontWeight: 600
        }} role="alert" aria-label="AI degraded mode warning">
          ⚠ AI Degraded: {aiCapabilities.degraded_features?.join(', ') || 'Some features unavailable'}.
          Missing/invalid provider keys are shown honestly.
        </div>
      )}

      {/* AI Tools inline toggle — only shown when hideInlineTools is false */}
      {!hideInlineTools && showAITools && handleTriggerLearning && (
        <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 0'}}>
          <button
            onClick={handleTriggerLearning}
            disabled={aiTaskLoading === 'learning' || isToolBlocked.learning}
            className="ai-tool-btn"
            title={isToolBlocked.learning ? (toolDisabledReason.learning || 'Unavailable') : ''}
          >
            {aiTaskLoading === 'learning' ? '⏳ Analyzing...' : '📚 AI Learning'}
          </button>
          <button
            onClick={handleEvolveBots}
            disabled={aiTaskLoading === 'evolve' || isToolBlocked.evolve}
            className="ai-tool-btn"
            title={isToolBlocked.evolve ? (toolDisabledReason.evolve || 'Unavailable') : ''}
          >
            {aiTaskLoading === 'evolve' ? '⏳ Evolving...' : '🧬 Evolve Bots'}
          </button>
          <button
            onClick={handleGetInsights}
            disabled={aiTaskLoading === 'insights' || isToolBlocked.insights}
            className="ai-tool-btn"
            title={isToolBlocked.insights ? (toolDisabledReason.insights || 'Unavailable') : ''}
          >
            {aiTaskLoading === 'insights' ? '⏳ Generating...' : '💡 AI Insights'}
          </button>
        </div>
      )}

      {/* Analytics inline toggle — only shown when hideInlineTools is false */}
      {!hideInlineTools && showAnalytics && handlePredictPrice && (
        <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 0'}}>
          <button
            onClick={handlePredictPrice}
            disabled={aiTaskLoading === 'predict' || isToolBlocked.predict}
            className="ai-tool-btn"
            title={isToolBlocked.predict ? (toolDisabledReason.predict || 'Unavailable') : ''}
          >
            {aiTaskLoading === 'predict' ? '⏳ Predicting...' : '🔮 ML Predict'}
          </button>
          <button
            onClick={handleReinvestProfits}
            disabled={aiTaskLoading === 'reinvest' || isToolBlocked.reinvest}
            className="ai-tool-btn"
            title={isToolBlocked.reinvest ? (toolDisabledReason.reinvest || 'Unavailable') : ''}
          >
            {aiTaskLoading === 'reinvest' ? '⏳ Reinvesting...' : '💰 Reinvest Profits'}
          </button>
        </div>
      )}

      <div className="amk-chat-box">
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`msg ${msg.role} ${msg.type || ''}`.trim()}>
            <div className="bubble">{msg.content}</div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      <div className="amk-row">
        {awaitingPassword ? (
          <input
            type="password"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleChatKeyDown}
            placeholder="Enter admin password..."
            disabled={chatSending}
          />
        ) : (
          <textarea
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleChatKeyDown}
            placeholder="Type a message or ask about AI reports... (Shift+Enter for new line)"
            rows={1}
            disabled={chatSending}
          />
        )}
        <button className="send" onClick={handleSendMessage} disabled={chatSending}>
          {chatSending ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  );
}
