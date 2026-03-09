// ARCHIVED: This file is not mounted in the dashboard and exists only for reference.
// Canonical section for this functionality lives elsewhere.
// NOTE: CoinStatsPanel has been replaced by MarketIntelligencePanel (canonical).
import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';
import MarketIntelligencePanel from './MarketIntelligencePanel';
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
        <div className="subsection-gap">
          <h3 className="subsection-label subsection-label--blue">Market Intelligence</h3>
          <MarketIntelligencePanel />
        </div>
        <div className="subsection-gap">
          <h3 className="subsection-label subsection-label--cyan">HuggingFace AI</h3>
          <HuggingFacePanel axiosConfig={axiosConfig} />
        </div>
      </div>
    </section>
  );
}
