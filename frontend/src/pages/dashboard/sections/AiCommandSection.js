import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';
import CoinStatsPanel from './CoinStatsPanel';
import HuggingFacePanel from './HuggingFacePanel';

export default function AiCommandSection({
  axiosConfig,
  awaitingPassword,
  chatEndRef,
  chatInput,
  chatMessages,
  chatSending,
  aiTaskLoading,
  handleChatKeyDown,
  handleClearChatHistory,
  handleEvolveBots,
  handleGetInsights,
  handlePredictPrice,
  handleReinvestProfits,
  handleSendMessage,
  handleTriggerLearning,
  loadChatHistory,
  setChatInput,
  setShowAITools,
  showAITools,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 AI Command"
          subtitle="AI interaction hub — chat, tools, market intelligence, and model integrations."
        />
        <AiChatSection
          awaitingPassword={awaitingPassword}
          chatEndRef={chatEndRef}
          chatInput={chatInput}
          chatMessages={chatMessages}
          chatSending={chatSending}
          aiTaskLoading={aiTaskLoading}
          handleChatKeyDown={handleChatKeyDown}
          handleClearChatHistory={handleClearChatHistory}
          handleEvolveBots={handleEvolveBots}
          handleGetInsights={handleGetInsights}
          handlePredictPrice={handlePredictPrice}
          handleReinvestProfits={handleReinvestProfits}
          handleSendMessage={handleSendMessage}
          handleTriggerLearning={handleTriggerLearning}
          loadChatHistory={loadChatHistory}
          setChatInput={setChatInput}
          setShowAITools={setShowAITools}
          showAITools={showAITools}
        />
        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#3B82F6', marginBottom: '16px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Market Intelligence</h3>
          <CoinStatsPanel axiosConfig={axiosConfig} />
        </div>
        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#06B6D4', marginBottom: '16px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>HuggingFace AI</h3>
          <HuggingFacePanel axiosConfig={axiosConfig} />
        </div>
      </div>
    </section>
  );
}
