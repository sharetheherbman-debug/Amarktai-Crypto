import React, { useState } from 'react';

export default function AiChatSection({
  chatMessages, chatEndRef, chatInput, setChatInput, chatSending, awaitingPassword,
  handleChatKeyDown, handleSendMessage, loadChatHistory, handleClearChatHistory,
  showAITools, setShowAITools, aiTaskLoading,
  handleTriggerLearning, handleEvolveBots, handleGetInsights, handlePredictPrice, handleReinvestProfits
}) {
  const [showAnalytics, setShowAnalytics] = useState(false);
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
          {setShowAITools && (
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
        </div>
        <div className={`amk-chat-indicator ${chatSending ? 'active' : ''}`}>
          {chatSending ? 'Sending...' : 'Ready'}
        </div>
        <img src="/assets/ai/ai-wave.svg" alt="" className="amk-chat-banner" />
      </div>

      {/* AI Tools inline toggle */}
      {showAITools && handleTriggerLearning && (
        <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 0'}}>
          <button
            onClick={handleTriggerLearning}
            disabled={aiTaskLoading === 'learning'}
            className="ai-tool-btn"
          >
            {aiTaskLoading === 'learning' ? '⏳ Analyzing...' : '📚 AI Learning'}
          </button>
          <button
            onClick={handleEvolveBots}
            disabled={aiTaskLoading === 'evolve'}
            className="ai-tool-btn"
          >
            {aiTaskLoading === 'evolve' ? '⏳ Evolving...' : '🧬 Evolve Bots'}
          </button>
          <button
            onClick={handleGetInsights}
            disabled={aiTaskLoading === 'insights'}
            className="ai-tool-btn"
          >
            {aiTaskLoading === 'insights' ? '⏳ Generating...' : '💡 AI Insights'}
          </button>
        </div>
      )}

      {/* Analytics inline toggle */}
      {showAnalytics && handlePredictPrice && (
        <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 0'}}>
          <button
            onClick={handlePredictPrice}
            disabled={aiTaskLoading === 'predict'}
            className="ai-tool-btn"
          >
            {aiTaskLoading === 'predict' ? '⏳ Predicting...' : '🔮 ML Predict'}
          </button>
          <button
            onClick={handleReinvestProfits}
            disabled={aiTaskLoading === 'reinvest'}
            className="ai-tool-btn"
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
