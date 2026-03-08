import SectionHeader from '@/ui/components/SectionHeader';
import AiChatSection from './AiChatSection';

export default function WelcomeSection({
  user,
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
  showAITools,
  setShowAITools,
}) {
  return (
    <section className="section active">
      <div className="card welcome-container">
        <SectionHeader
          title={`Welcome, ${user?.first_name || 'Trader'}`}
          subtitle="Your AI trading command center — chat with the AI and trigger live actions."
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
          hideInlineTools={false}
        />
      </div>
    </section>
  );
}
