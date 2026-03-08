import { useState } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';

const tabStyle = (active) => ({
  padding: '10px 20px',
  fontSize: '0.9rem',
  fontWeight: 600,
  background: active ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
  color: active ? '#3B82F6' : 'var(--muted)',
  border: '1px solid',
  borderColor: active ? 'rgba(59, 130, 246, 0.4)' : 'var(--line)',
  borderRadius: '8px',
  cursor: 'pointer',
  transition: 'all 0.2s ease',
});

const toolBtnStyle = (loading) => ({
  padding: '12px 18px',
  fontSize: '0.85rem',
  fontWeight: 600,
  background: loading ? 'rgba(59, 130, 246, 0.3)' : 'rgba(10, 14, 26, 0.85)',
  color: 'var(--text)',
  border: '1px solid var(--line)',
  borderRadius: '12px',
  cursor: loading ? 'not-allowed' : 'pointer',
  opacity: loading ? 0.7 : 1,
  transition: 'all 0.2s ease',
  minWidth: '150px',
  textAlign: 'center',
});

export default function WelcomeSection({
  axiosConfig,
  user,
  showSection,
  showAITools,
  setShowAITools,
  aiTaskLoading,
  handleTriggerLearning,
  handleEvolveBots,
  handleGetInsights,
  handlePredictPrice,
  handleReinvestProfits,
  chatMessages,
  chatEndRef,
  chatInput,
  setChatInput,
  chatSending,
  awaitingPassword,
  handleChatKeyDown,
  handleSendMessage,
  loadChatHistory,
  handleClearChatHistory,
}) {
  const [activeTab, setActiveTab] = useState('chat');

  return (
    <section className="section active">
      <div className="card welcome-container">
        <SectionHeader
          title={`Welcome, ${user?.first_name || 'Trader'}`}
          subtitle="Your AI trading command center — chat, tools, and analytics."
        />

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <button style={tabStyle(activeTab === 'chat')} onClick={() => setActiveTab('chat')}>
            💬 AI Chat
          </button>
          <button style={tabStyle(activeTab === 'tools')} onClick={() => setActiveTab('tools')}>
            🧠 AI Tools
          </button>
          <button style={tabStyle(activeTab === 'analytics')} onClick={() => setActiveTab('analytics')}>
            📊 AI Analytics
          </button>
        </div>

        {/* AI Chat Tab */}
        {activeTab === 'chat' && (
          <AiChatSection
            chatMessages={chatMessages}
            chatEndRef={chatEndRef}
            chatInput={chatInput}
            setChatInput={setChatInput}
            chatSending={chatSending}
            awaitingPassword={awaitingPassword}
            handleChatKeyDown={handleChatKeyDown}
            handleSendMessage={handleSendMessage}
            loadChatHistory={loadChatHistory}
            handleClearChatHistory={handleClearChatHistory}
            hideInlineTools={true}
          />
        )}

        {/* AI Tools Tab */}
        {activeTab === 'tools' && (
          <div style={{ padding: '8px 0' }}>
            <p style={{ color: 'var(--muted)', marginBottom: '16px', fontSize: '0.9rem' }}>
              Trigger AI-powered operations on your trading system.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px' }}>
              <button
                style={toolBtnStyle(aiTaskLoading === 'learning')}
                onClick={handleTriggerLearning}
                disabled={aiTaskLoading === 'learning'}
              >
                📚 {aiTaskLoading === 'learning' ? 'Analyzing...' : 'AI Learning'}
              </button>
              <button
                style={toolBtnStyle(aiTaskLoading === 'evolve')}
                onClick={handleEvolveBots}
                disabled={aiTaskLoading === 'evolve'}
              >
                🧬 {aiTaskLoading === 'evolve' ? 'Evolving...' : 'Evolve Bots'}
              </button>
              <button
                style={toolBtnStyle(aiTaskLoading === 'insights')}
                onClick={handleGetInsights}
                disabled={aiTaskLoading === 'insights'}
              >
                💡 {aiTaskLoading === 'insights' ? 'Generating...' : 'AI Insights'}
              </button>
              <button
                style={toolBtnStyle(aiTaskLoading === 'reinvest')}
                onClick={handleReinvestProfits}
                disabled={aiTaskLoading === 'reinvest'}
              >
                💰 {aiTaskLoading === 'reinvest' ? 'Processing...' : 'Reinvest Profits'}
              </button>
            </div>
            <div style={{
              marginTop: '20px',
              padding: '16px',
              background: 'rgba(59, 130, 246, 0.08)',
              border: '1px solid var(--line)',
              borderRadius: '12px',
            }}>
              <h4 style={{ color: 'var(--text)', marginBottom: '8px', fontSize: '0.95rem' }}>How AI Tools Work</h4>
              <ul style={{ color: 'var(--muted)', fontSize: '0.85rem', paddingLeft: '18px', lineHeight: '1.8' }}>
                <li><strong>AI Learning</strong> — Analyzes recent trades to improve bot strategies</li>
                <li><strong>Evolve Bots</strong> — Applies genetic algorithm optimization to active bots</li>
                <li><strong>AI Insights</strong> — Generates market and portfolio intelligence reports</li>
                <li><strong>Reinvest Profits</strong> — Allocates realized profits to top-performing bots</li>
              </ul>
            </div>
          </div>
        )}

        {/* AI Analytics Tab */}
        {activeTab === 'analytics' && (
          <div style={{ padding: '8px 0' }}>
            <p style={{ color: 'var(--muted)', marginBottom: '16px', fontSize: '0.9rem' }}>
              AI-driven market predictions and analysis.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px' }}>
              <button
                style={toolBtnStyle(aiTaskLoading === 'predict')}
                onClick={handlePredictPrice}
                disabled={aiTaskLoading === 'predict'}
              >
                🔮 {aiTaskLoading === 'predict' ? 'Predicting...' : 'ML Price Prediction'}
              </button>
            </div>
            <div style={{
              marginTop: '20px',
              padding: '16px',
              background: 'rgba(34, 197, 94, 0.08)',
              border: '1px solid var(--line)',
              borderRadius: '12px',
            }}>
              <h4 style={{ color: 'var(--text)', marginBottom: '8px', fontSize: '0.95rem' }}>Analytics Overview</h4>
              <ul style={{ color: 'var(--muted)', fontSize: '0.85rem', paddingLeft: '18px', lineHeight: '1.8' }}>
                <li><strong>ML Predictions</strong> — Machine learning price forecasts for your trading pairs</li>
                <li><strong>Market Sentiment</strong> — Access via the AI Chat tab for detailed analysis</li>
                <li><strong>Performance Insights</strong> — See Profits &amp; Performance for detailed charts</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
