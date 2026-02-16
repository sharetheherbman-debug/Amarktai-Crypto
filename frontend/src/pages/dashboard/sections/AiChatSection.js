import React from 'react';

export default function AiChatSection({ chatMessages, chatEndRef, chatInput, setChatInput, chatSending, awaitingPassword, handleChatKeyDown, handleSendMessage, loadChatHistory, handleClearChatHistory }) {
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
        </div>
        <div className={`amk-chat-indicator ${chatSending ? 'active' : ''}`}>
          {chatSending ? 'Sending...' : 'Ready'}
        </div>
        <img src="/assets/ai/ai-wave.svg" alt="" className="amk-chat-banner" />
      </div>
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
