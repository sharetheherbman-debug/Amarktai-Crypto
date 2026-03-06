import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';
import CoinStatsPanel from './CoinStatsPanel';
import HuggingFacePanel from './HuggingFacePanel';

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
  return (
    <section className="section active">
      <div className="card welcome-container">
        <SectionHeader
          title={`Welcome, ${user?.first_name || 'Trader'}`}
          subtitle="Control your AI trading system with quick actions or natural language."
        />
        
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
          showAITools={showAITools}
          setShowAITools={setShowAITools}
          aiTaskLoading={aiTaskLoading}
          handleTriggerLearning={handleTriggerLearning}
          handleEvolveBots={handleEvolveBots}
          handleGetInsights={handleGetInsights}
          handlePredictPrice={handlePredictPrice}
          handleReinvestProfits={handleReinvestProfits}
        />
      </div>
      <CoinStatsPanel axiosConfig={axiosConfig} />
      <HuggingFacePanel axiosConfig={axiosConfig} />
    </section>
  );
}
