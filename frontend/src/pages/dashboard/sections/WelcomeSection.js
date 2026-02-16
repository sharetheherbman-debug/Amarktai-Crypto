import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';

export default function WelcomeSection({
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
  return (
    <section className="section active">
      <div className="card welcome-container">
        <SectionHeader
          title={`Welcome, ${user?.first_name || 'Trader'}`}
          subtitle="Control your AI trading system with quick actions or natural language."
          action={(
            <div className="welcome-actions">
              <button type="button" className="btn-secondary" onClick={() => showSection('api')}>
                API Setup
              </button>
              <button type="button" className="btn-secondary" onClick={() => showSection('bots')}>
                Create Bot
              </button>
              <button type="button" className="btn-secondary" onClick={() => showSection('system')}>
                System Mode
              </button>
            </div>
          )}
        />
        
        {/* AI Tools Toggle Button */}
        <div style={{marginBottom: '16px'}}>
          <button 
            onClick={() => setShowAITools(!showAITools)}
            style={{
              width: '100%',
              padding: '12px 16px',
              background: showAITools ? 'linear-gradient(135deg, rgba(56, 189, 248, 0.9) 0%, rgba(56, 189, 248, 0.6) 100%)' : 'var(--panel)',
              color: 'var(--text)',
              border: '1px solid rgba(56, 189, 248, 0.4)',
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
        <div style={{marginBottom: '20px', padding: '16px', background: 'var(--panel)', borderRadius: '12px', border: '1px solid var(--line)'}}>
          <p style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '12px'}}>
            ⚡ All reports appear in the chat below. Ask questions about results!
          </p>
          
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
              <button
                onClick={handleTriggerLearning}
                disabled={aiTaskLoading === 'learning'}
                style={{padding: '12px', background: aiTaskLoading === 'learning' ? '#666' : 'linear-gradient(135deg, rgba(56, 189, 248, 0.9) 0%, rgba(56, 189, 248, 0.6) 100%)', color: '#0b0d14', border: 'none', borderRadius: '999px', cursor: aiTaskLoading === 'learning' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'learning' ? 0.7 : 1}}
              >
                {aiTaskLoading === 'learning' ? '⏳ Analyzing...' : '📚 AI Learning'}
              </button>
            
              <button 
                onClick={handleEvolveBots}
                disabled={aiTaskLoading === 'evolve'}
                style={{padding: '12px', background: aiTaskLoading === 'evolve' ? '#666' : 'linear-gradient(135deg, rgba(34, 197, 94, 0.9) 0%, rgba(34, 197, 94, 0.6) 100%)', color: '#0b0d14', border: 'none', borderRadius: '999px', cursor: aiTaskLoading === 'evolve' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'evolve' ? 0.7 : 1}}
              >
                {aiTaskLoading === 'evolve' ? '⏳ Evolving...' : '🧬 Evolve Bots'}
              </button>
            
              <button 
                onClick={handleGetInsights}
                disabled={aiTaskLoading === 'insights'}
                style={{padding: '12px', background: aiTaskLoading === 'insights' ? '#666' : 'linear-gradient(135deg, rgba(56, 189, 248, 0.9) 0%, rgba(34, 197, 94, 0.6) 100%)', color: '#0b0d14', border: 'none', borderRadius: '999px', cursor: aiTaskLoading === 'insights' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'insights' ? 0.7 : 1}}
              >
                {aiTaskLoading === 'insights' ? '⏳ Generating...' : '💡 AI Insights'}
              </button>
            
              <button 
                onClick={handlePredictPrice}
                disabled={aiTaskLoading === 'predict'}
                style={{padding: '12px', background: aiTaskLoading === 'predict' ? '#666' : 'linear-gradient(135deg, rgba(56, 189, 248, 0.85) 0%, rgba(56, 189, 248, 0.55) 100%)', color: '#0b0d14', border: 'none', borderRadius: '999px', cursor: aiTaskLoading === 'predict' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'predict' ? 0.7 : 1}}
              >
                {aiTaskLoading === 'predict' ? '⏳ Predicting...' : '🔮 ML Predict'}
              </button>
            
              <button 
                onClick={handleReinvestProfits}
                disabled={aiTaskLoading === 'reinvest'}
                style={{padding: '12px', background: aiTaskLoading === 'reinvest' ? '#666' : 'linear-gradient(135deg, rgba(34, 197, 94, 0.9) 0%, rgba(34, 197, 94, 0.6) 100%)', color: '#0b0d14', border: 'none', borderRadius: '999px', cursor: aiTaskLoading === 'reinvest' ? 'wait' : 'pointer', fontWeight: 600, fontSize: '0.9rem', opacity: aiTaskLoading === 'reinvest' ? 0.7 : 1}}
              >
                {aiTaskLoading === 'reinvest' ? '⏳ Reinvesting...' : '💰 Reinvest Profits'}
              </button>
          </div>
        </div>
        )}
        
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
        />
      </div>
    </section>
  );
}
