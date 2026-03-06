import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import './DashboardV3.css';
import ErrorBoundary from '../components/ErrorBoundary';
import SiteFooter from '../components/SiteFooter';
import Brand from '../components/Brand';
import useDashboardState from '../hooks/useDashboardState';
import Badge from '@/ui/components/Badge';
import ModalConfirm from '@/ui/components/ModalConfirm';
import WelcomeSection from './dashboard/sections/WelcomeSection';
import OverviewSection from './dashboard/sections/OverviewSection';
import ProfileSection from './dashboard/sections/ProfileSection';
import AdminPanelSection from './dashboard/sections/AdminPanelSection';
import SystemModeSection from './dashboard/sections/SystemModeSection';
import LiveTradesSection from './dashboard/sections/LiveTradesSection';
import ProfitsSection from './dashboard/sections/ProfitsSection';
import CountdownSection from './dashboard/sections/CountdownSection';
import WalletHubSection from './dashboard/sections/WalletHubSection';
import ApiSetupSection from './dashboard/sections/ApiSetupSection';
import BotManagementSection from './dashboard/sections/BotManagementSection';
import MetricsWithTabsSection from './dashboard/sections/MetricsWithTabsSection';
import BotRadarSection from './dashboard/sections/BotRadarSection';
import ExchangeStatusSection from './dashboard/sections/ExchangeStatusSection';
import TruthConsoleSection from './dashboard/sections/TruthConsoleSection';
import CoinStatsPanel from './dashboard/sections/CoinStatsPanel';
import HuggingFacePanel from './dashboard/sections/HuggingFacePanel';
import HomeSection from './dashboard/sections/HomeSection';
import AiCommandSection from './dashboard/sections/AiCommandSection';
import BotOperationsSection from './dashboard/sections/BotOperationsSection';
import TradingMonitorSection from './dashboard/sections/TradingMonitorSection';
import PerformanceSection from './dashboard/sections/PerformanceSection';
import WalletTreasurySection from './dashboard/sections/WalletTreasurySection';
import ProfileControlsSection from './dashboard/sections/ProfileControlsSection';
import AdminTruthSection from './dashboard/sections/AdminTruthSection';
import { NAV, NAV_LABELS } from '../constants/dashboardNav';
import '../styles/radar-exchange.css';
import '../styles/truth-console.css';
import '../styles/scalper-panel.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};


export default function Dashboard() {
  const navigate = useNavigate();

  const {
    actionLoading,
    activeBotTab,
    activeSection,
    addCustomCountdown,
    adminApiHealth,
    adminBots,
    adminUsers,
    aiStatus,
    aiTaskLoading,
    allUsers,
    autoSpawnStatus,
    autonomyStatus,
    autopilotReinvestStatus,
    awaitingPassword,
    axiosConfig,
    balances,
    bodyguardStatus,
    botControlLoading,
    botDetailTab,
    botManagementTab,
    botSetup,
    botStatusFilter,
    bots,
    chatEndRef,
    chatInput,
    chatMessages,
    chatSending,
    clearUserEmergencyOverride,
    confirmLiveSwitch,
    connectionStatus,
    countdown,
    customCountdowns,
    deleteCustomCountdown,
    drawdownData,
    drawdownRange,
    editingBotId,
    editingBotName,
    eligibleBots,
    emergencyOverrideStatus,
    equityData,
    equityRange,
    executeEmergencyStop,
    filteredAdminBots,
    formatDate,
    getAlertColor,
    graphPeriod,
    handleBlockUser,
    handleBotSetup,
    handleChangeBotExchange,
    handleChangeBotMode,
    handleChangePassword,
    handleChatKeyDown,
    handleClearChatHistory,
    handleCreateBot,
    handleCreateUAgent,
    handleDeleteBot,
    handleDeleteUser,
    handleDeleteUserAdmin,
    handleEmailAllUsers,
    handleEmergencyStop,
    handleEvolveBots,
    handleForceLogout,
    handleGetInsights,
    handleLogout,
    handleMigrateApiKeys,
    handlePaperReset,
    handlePredictPrice,
    handleProfileChange,
    handleProfileSave,
    handleReinvestProfits,
    handleRenameBotSubmit,
    handleResetBodyguardLock,
    handleResetDailyLossLock,
    handleResetPassword,
    handleResumeAllBots,
    handleResumeBot,
    handleRiskProfileChange,
    handleSendMessage,
    handleStartBot,
    handleToggleBlockUser,
    handleToggleBotMode,
    handleToggleBotPause,
    handleTriggerBodyguard,
    handleTriggerLearning,
    handleUserSelection,
    isMobile,
    learningStatus,
    livePrices,
    loadAdminBots,
    loadAdminUsers,
    loadChatHistory,
    loadingBots,
    loadingUsers,
    metrics,
    metricsTab,
    modeLabel,
    modeTone,
    newCountdownAmount,
    newCountdownLabel,
    overviewData,
    paperResetChecking,
    paperResetError,
    paperResetLoading,
    paperResetPassword,
    paperResetValid,
    platformFilter,
    profileData,
    profitData,
    profitsTab,
    realtimeConnected,
    realtimeLabel,
    realtimeTone,
    recentTrades,
    riskLabel,
    riskProfile,
    riskStatus,
    riskTone,
    selectedBotDetailId,
    selectedBotId,
    selectedTradeId,
    selectedUserId,
    setActiveBotTab,
    setActiveSection,
    setBotDetailTab,
    setBotManagementTab,
    setBotSetup,
    setBotStatusFilter,
    setChatInput,
    setChatMessages,
    setDrawdownRange,
    setEditingBotId,
    setEditingBotName,
    setEquityRange,
    setGraphPeriod,
    setMetricsTab,
    setNewCountdownAmount,
    setNewCountdownLabel,
    setPaperResetError,
    setPaperResetPassword,
    setPaperResetValid,
    setPlatformFilter,
    setProfitsTab,
    setSelectedBotDetailId,
    setSelectedBotId,
    setSelectedTradeId,
    setSelectedUserId,
    setShowAITools,
    setShowAddCountdown,
    setShowEmergencyConfirm,
    setShowPaperResetModal,
    setShowPromotionModal,
    setTradeBotFilter,
    setTradeExchangeFilter,
    setTradePairFilter,
    setWinRatePeriod,
    showAITools,
    showAddCountdown,
    showAdmin,
    showEmergencyConfirm,
    showNotification,
    showPaperResetModal,
    showPromotionModal,
    showSection,
    storageData,
    storageError,
    storageTotals,
    systemModes,
    systemStats,
    toggleSystemMode,
    tradeBotFilter,
    tradeExchangeFilter,
    tradePairFilter,
    updateGlobalEmergencyOverride,
    updateUserEmergencyOverride,
    user,
    userInitial,
    winRateData,
    winRatePeriod,
  } = useDashboardState(navigate);

  const renderMetricsWithTabs = () => (
    <MetricsWithTabsSection
      metrics={metrics}
      metricsTab={metricsTab}
      setMetricsTab={setMetricsTab}
    />
  );

  const renderWelcome = () => (
    <WelcomeSection
      axiosConfig={axiosConfig}
      user={user}
      showSection={showSection}
      showAITools={showAITools}
      setShowAITools={setShowAITools}
      aiTaskLoading={aiTaskLoading}
      handleTriggerLearning={handleTriggerLearning}
      handleEvolveBots={handleEvolveBots}
      handleGetInsights={handleGetInsights}
      handlePredictPrice={handlePredictPrice}
      handleReinvestProfits={handleReinvestProfits}
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
  );

  const renderOverview = () => (
    <OverviewSection
      user={user}
      aiStatus={aiStatus}
      autonomyStatus={autonomyStatus}
      botControlLoading={botControlLoading}
      formatDate={formatDate}
      handleResetBodyguardLock={handleResetBodyguardLock}
      handleResetDailyLossLock={handleResetDailyLossLock}
      handleResumeAllBots={handleResumeAllBots}
      learningStatus={learningStatus}
      livePrices={livePrices}
      metrics={metrics}
      modeLabel={modeLabel}
      overviewData={overviewData}
      riskStatus={riskStatus}
      systemModes={systemModes}
    />
  );

  const renderProfile = () => (
    <ProfileSection
      user={user}
      bots={bots}
      formatDate={formatDate}
      profileData={profileData}
      handleProfileChange={handleProfileChange}
      handleProfileSave={handleProfileSave}
      handleEmergencyStop={handleEmergencyStop}
    />
  );

  // Handle API Key Migration

  const renderAdmin = () => (
    <AdminPanelSection
      user={user}
      actionLoading={actionLoading}
      adminApiHealth={adminApiHealth}
      adminBots={adminBots}
      adminUsers={adminUsers}
      aiTaskLoading={aiTaskLoading}
      allUsers={allUsers}
      axiosConfig={axiosConfig}
      bodyguardStatus={bodyguardStatus}
      bots={bots}
      clearUserEmergencyOverride={clearUserEmergencyOverride}
      emergencyOverrideStatus={emergencyOverrideStatus}
      filteredAdminBots={filteredAdminBots}
      formatDate={formatDate}
      handleBlockUser={handleBlockUser}
      handleChangeBotExchange={handleChangeBotExchange}
      handleChangeBotMode={handleChangeBotMode}
      handleChangePassword={handleChangePassword}
      handleDeleteUser={handleDeleteUser}
      handleDeleteUserAdmin={handleDeleteUserAdmin}
      handleEmailAllUsers={handleEmailAllUsers}
      handleForceLogout={handleForceLogout}
      handleMigrateApiKeys={handleMigrateApiKeys}
      handleResetPassword={handleResetPassword}
      handleToggleBlockUser={handleToggleBlockUser}
      handleToggleBotPause={handleToggleBotPause}
      handleTriggerBodyguard={handleTriggerBodyguard}
      handleUserSelection={handleUserSelection}
      loadAdminUsers={loadAdminUsers}
      loadAdminBots={loadAdminBots}
      loadingBots={loadingBots}
      loadingUsers={loadingUsers}
      selectedBotId={selectedBotId}
      selectedUserId={selectedUserId}
      setActiveSection={setActiveSection}
      setChatMessages={setChatMessages}
      setSelectedBotId={setSelectedBotId}
      setSelectedUserId={setSelectedUserId}
      showNotification={showNotification}
      showSection={showSection}
      storageData={storageData}
      storageError={storageError}
      storageTotals={storageTotals}
      systemStats={systemStats}
      updateGlobalEmergencyOverride={updateGlobalEmergencyOverride}
      updateUserEmergencyOverride={updateUserEmergencyOverride}
    />
  );

  const renderSystemMode = () => (
    <SystemModeSection
      bots={bots}
      handleEmergencyStop={handleEmergencyStop}
      handlePaperReset={handlePaperReset}
      handleRiskProfileChange={handleRiskProfileChange}
      paperResetChecking={paperResetChecking}
      paperResetError={paperResetError}
      paperResetLoading={paperResetLoading}
      paperResetPassword={paperResetPassword}
      paperResetValid={paperResetValid}
      riskProfile={riskProfile}
      setPaperResetError={setPaperResetError}
      setPaperResetPassword={setPaperResetPassword}
      setPaperResetValid={setPaperResetValid}
      setShowPaperResetModal={setShowPaperResetModal}
      showPaperResetModal={showPaperResetModal}
      systemModes={systemModes}
      toggleSystemMode={toggleSystemMode}
    />
  );

  const renderLiveTradeFeed = () => (
    <LiveTradesSection
      recentTrades={recentTrades}
      selectedTradeId={selectedTradeId}
      setSelectedTradeId={setSelectedTradeId}
      setTradeBotFilter={setTradeBotFilter}
      setTradeExchangeFilter={setTradeExchangeFilter}
      setTradePairFilter={setTradePairFilter}
      tradeBotFilter={tradeBotFilter}
      tradeExchangeFilter={tradeExchangeFilter}
      tradePairFilter={tradePairFilter}
    />
  );

  const renderProfitGraphs = () => (
    <ProfitsSection
      bots={bots}
      drawdownData={drawdownData}
      drawdownRange={drawdownRange}
      equityData={equityData}
      equityRange={equityRange}
      formatDate={formatDate}
      getAlertColor={getAlertColor}
      graphPeriod={graphPeriod}
      overviewData={overviewData}
      profitData={profitData}
      profitsTab={profitsTab}
      setDrawdownRange={setDrawdownRange}
      setEquityRange={setEquityRange}
      setGraphPeriod={setGraphPeriod}
      setProfitsTab={setProfitsTab}
      setWinRatePeriod={setWinRatePeriod}
      showSection={showSection}
      winRateData={winRateData}
      winRatePeriod={winRatePeriod}
      metricsTab={metricsTab}
      setMetricsTab={setMetricsTab}
      renderMetricsWithTabs={renderMetricsWithTabs}
    />
  );

  const renderCountdown = () => (
    <CountdownSection
      countdown={countdown}
      customCountdowns={customCountdowns}
      metrics={metrics}
      newCountdownAmount={newCountdownAmount}
      newCountdownLabel={newCountdownLabel}
      setNewCountdownAmount={setNewCountdownAmount}
      setNewCountdownLabel={setNewCountdownLabel}
      setShowAddCountdown={setShowAddCountdown}
      showAddCountdown={showAddCountdown}
      addCustomCountdown={addCustomCountdown}
      deleteCustomCountdown={deleteCustomCountdown}
    />
  );

  const renderWalletHub = () => (
    <WalletHubSection
      balances={balances}
      systemModes={systemModes}
    />
  );

  const renderAPIKeys = () => (
    <ApiSetupSection />
  );

  const renderApiSetup = renderAPIKeys;

  const renderBots = () => (
    <BotManagementSection
      autoSpawnStatus={autoSpawnStatus}
      autopilotReinvestStatus={autopilotReinvestStatus}
      botDetailTab={botDetailTab}
      botManagementTab={botManagementTab}
      botStatusFilter={botStatusFilter}
      bots={bots}
      formatDate={formatDate}
      handleCreateBot={handleCreateBot}
      handleCreateUAgent={handleCreateUAgent}
      handleDeleteBot={handleDeleteBot}
      handleResumeBot={handleResumeBot}
      handleStartBot={handleStartBot}
      handleToggleBotMode={handleToggleBotMode}
      platformFilter={platformFilter}
      selectedBotDetailId={selectedBotDetailId}
      setBotDetailTab={setBotDetailTab}
      setBotManagementTab={setBotManagementTab}
      setBotStatusFilter={setBotStatusFilter}
      setPlatformFilter={setPlatformFilter}
      setSelectedBotDetailId={setSelectedBotDetailId}
      botSetup={botSetup}
      setBotSetup={setBotSetup}
      activeBotTab={activeBotTab}
      setActiveBotTab={setActiveBotTab}
      editingBotId={editingBotId}
      setEditingBotId={setEditingBotId}
      editingBotName={editingBotName}
      setEditingBotName={setEditingBotName}
      handleBotSetup={handleBotSetup}
      botControlLoading={botControlLoading}
      handleRenameBotSubmit={handleRenameBotSubmit}
      axiosConfig={axiosConfig}
    />
  );


  return (
    <div className="app">
      {/* Sidebar - Desktop */}
      {!isMobile && (
        <aside className="sidebar">
          <img
            src="/assets/logo.png"
            className="logo sidebar-logo"
            alt="Amarktai Crypto"
            onClick={() => showSection(NAV.HOME)}
            style={{ cursor: 'pointer' }}
          />
          <div className="sidebar-brand-text">AMARKTAI CRYPTO AI</div>
          <nav className="nav" key={`nav-${showAdmin}`}>
            <a href="#" className={activeSection === NAV.HOME ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.HOME); }}>{NAV_LABELS[NAV.HOME]}</a>
            <a href="#" className={activeSection === NAV.AI_COMMAND ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.AI_COMMAND); }}>{NAV_LABELS[NAV.AI_COMMAND]}</a>
            <a href="#" className={activeSection === NAV.BOT_OPERATIONS ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.BOT_OPERATIONS); }}>{NAV_LABELS[NAV.BOT_OPERATIONS]}</a>
            <a href="#" className={activeSection === NAV.TRADING_MONITOR ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.TRADING_MONITOR); }}>{NAV_LABELS[NAV.TRADING_MONITOR]}</a>
            <a href="#" className={activeSection === NAV.PERFORMANCE ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.PERFORMANCE); }}>{NAV_LABELS[NAV.PERFORMANCE]}</a>
            <a href="#" className={activeSection === NAV.COUNTDOWN ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.COUNTDOWN); }}>{NAV_LABELS[NAV.COUNTDOWN]}</a>
            <a href="#" className={activeSection === NAV.WALLET_TREASURY ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.WALLET_TREASURY); }}>{NAV_LABELS[NAV.WALLET_TREASURY]}</a>
            <a href="#" className={activeSection === NAV.PROFILE_CONTROLS ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.PROFILE_CONTROLS); }}>{NAV_LABELS[NAV.PROFILE_CONTROLS]}</a>
            {showAdmin && (
              <a href="#" className={activeSection === NAV.ADMIN_TRUTH ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.ADMIN_TRUTH); }}>{NAV_LABELS[NAV.ADMIN_TRUTH]}</a>
            )}
          </nav>
        </aside>
      )}

      {/* Topbar - Desktop */}
      {!isMobile && (
        <header className="topbar">
            <div className="topbar-brand">
              <div className="topbar-title"><Brand /></div>
            </div>
          <div className="top-actions">
            <Badge variant={modeTone} className="topbar-badge">
              {modeLabel} MODE
            </Badge>
            <Badge variant={realtimeTone} className="topbar-badge">
              {realtimeLabel}
            </Badge>
            <Badge variant={riskTone} className="topbar-badge">
              Risk {riskLabel}
            </Badge>
            <button className="logout-btn" onClick={handleLogout}>Logout</button>
          </div>
        </header>
      )}

      {/* Mobile Topbar */}
      {isMobile && (
        <div className="mobile-topbar">
          <button className="mobile-logo-btn" onClick={() => showSection(NAV.HOME)}>
            <img
              src="/assets/logo.png"
              className="mobile-logo"
              alt="Amarktai Crypto"
            />
          </button>
          <div className="mobile-btns">
            <button className="mobile-btn" onClick={() => showSection(NAV.HOME)}>Home</button>
            <button className="mobile-btn" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="main"> 
        {activeSection === NAV.HOME && (
          <ErrorBoundary title="Home section error" message="Unable to load Home section.">
            <HomeSection
              countdown={countdown}
              showSection={showSection}
              aiStatus={aiStatus}
              autonomyStatus={autonomyStatus}
              botControlLoading={botControlLoading}
              bots={bots}
              connectionStatus={connectionStatus}
              formatDate={formatDate}
              handleResetBodyguardLock={handleResetBodyguardLock}
              handleResetDailyLossLock={handleResetDailyLossLock}
              handleResumeAllBots={handleResumeAllBots}
              learningStatus={learningStatus}
              livePrices={livePrices}
              metrics={metrics}
              modeLabel={modeLabel}
              modeTone={modeTone}
              overviewData={overviewData}
              realtimeConnected={realtimeConnected}
              realtimeLabel={realtimeLabel}
              realtimeTone={realtimeTone}
              riskLabel={riskLabel}
              riskStatus={riskStatus}
              riskTone={riskTone}
              systemModes={systemModes}
              user={user}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.AI_COMMAND && (
          <ErrorBoundary title="AI Command error" message="Unable to load AI Command section.">
            <AiCommandSection
              axiosConfig={axiosConfig}
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
          </ErrorBoundary>
        )}
        {activeSection === NAV.BOT_OPERATIONS && (
          <ErrorBoundary title="Bot Operations error" message="Unable to load Bot Operations section.">
            <BotOperationsSection
              autoSpawnStatus={autoSpawnStatus}
              autopilotReinvestStatus={autopilotReinvestStatus}
              botDetailTab={botDetailTab}
              botManagementTab={botManagementTab}
              botStatusFilter={botStatusFilter}
              bots={bots}
              formatDate={formatDate}
              handleCreateBot={handleCreateBot}
              handleCreateUAgent={handleCreateUAgent}
              handleDeleteBot={handleDeleteBot}
              handleResumeBot={handleResumeBot}
              handleStartBot={handleStartBot}
              handleToggleBotMode={handleToggleBotMode}
              platformFilter={platformFilter}
              selectedBotDetailId={selectedBotDetailId}
              setBotDetailTab={setBotDetailTab}
              setBotManagementTab={setBotManagementTab}
              setBotStatusFilter={setBotStatusFilter}
              setPlatformFilter={setPlatformFilter}
              setSelectedBotDetailId={setSelectedBotDetailId}
              botSetup={botSetup}
              setBotSetup={setBotSetup}
              activeBotTab={activeBotTab}
              setActiveBotTab={setActiveBotTab}
              editingBotId={editingBotId}
              setEditingBotId={setEditingBotId}
              editingBotName={editingBotName}
              setEditingBotName={setEditingBotName}
              handleBotSetup={handleBotSetup}
              botControlLoading={botControlLoading}
              handleRenameBotSubmit={handleRenameBotSubmit}
              axiosConfig={axiosConfig}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.TRADING_MONITOR && (
          <ErrorBoundary title="Trading Monitor error" message="Unable to load Trading Monitor section.">
            <TradingMonitorSection
              axiosConfig={axiosConfig}
              recentTrades={recentTrades}
              selectedTradeId={selectedTradeId}
              setSelectedTradeId={setSelectedTradeId}
              setTradeBotFilter={setTradeBotFilter}
              setTradeExchangeFilter={setTradeExchangeFilter}
              setTradePairFilter={setTradePairFilter}
              tradeBotFilter={tradeBotFilter}
              tradeExchangeFilter={tradeExchangeFilter}
              tradePairFilter={tradePairFilter}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.PERFORMANCE && (
          <ErrorBoundary title="Performance error" message="Unable to load Performance section.">
            <PerformanceSection
              bots={bots}
              drawdownData={drawdownData}
              drawdownRange={drawdownRange}
              equityData={equityData}
              equityRange={equityRange}
              formatDate={formatDate}
              getAlertColor={getAlertColor}
              graphPeriod={graphPeriod}
              overviewData={overviewData}
              profitData={profitData}
              profitsTab={profitsTab}
              setDrawdownRange={setDrawdownRange}
              setEquityRange={setEquityRange}
              setGraphPeriod={setGraphPeriod}
              setProfitsTab={setProfitsTab}
              setWinRatePeriod={setWinRatePeriod}
              showSection={showSection}
              winRateData={winRateData}
              winRatePeriod={winRatePeriod}
              metricsTab={metricsTab}
              setMetricsTab={setMetricsTab}
              renderMetricsWithTabs={renderMetricsWithTabs}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.COUNTDOWN && (
          <ErrorBoundary title="Countdown section error" message="Unable to load Countdown section.">
            <CountdownSection
              countdown={countdown}
              customCountdowns={customCountdowns}
              metrics={metrics}
              newCountdownAmount={newCountdownAmount}
              newCountdownLabel={newCountdownLabel}
              setNewCountdownAmount={setNewCountdownAmount}
              setNewCountdownLabel={setNewCountdownLabel}
              setShowAddCountdown={setShowAddCountdown}
              showAddCountdown={showAddCountdown}
              addCustomCountdown={addCustomCountdown}
              deleteCustomCountdown={deleteCustomCountdown}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.WALLET_TREASURY && (
          <ErrorBoundary title="Wallet & Treasury error" message="Unable to load Wallet & Treasury section.">
            <WalletTreasurySection
              balances={balances}
              systemModes={systemModes}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.PROFILE_CONTROLS && (
          <ErrorBoundary title="Profile & Controls error" message="Unable to load Profile & Controls section.">
            <ProfileControlsSection
              user={user}
              bots={bots}
              formatDate={formatDate}
              profileData={profileData}
              handleProfileChange={handleProfileChange}
              handleProfileSave={handleProfileSave}
              handleEmergencyStop={handleEmergencyStop}
              handlePaperReset={handlePaperReset}
              handleRiskProfileChange={handleRiskProfileChange}
              paperResetChecking={paperResetChecking}
              paperResetError={paperResetError}
              paperResetLoading={paperResetLoading}
              paperResetPassword={paperResetPassword}
              paperResetValid={paperResetValid}
              riskProfile={riskProfile}
              setPaperResetError={setPaperResetError}
              setPaperResetPassword={setPaperResetPassword}
              setPaperResetValid={setPaperResetValid}
              setShowPaperResetModal={setShowPaperResetModal}
              showPaperResetModal={showPaperResetModal}
              systemModes={systemModes}
              toggleSystemMode={toggleSystemMode}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.ADMIN_TRUTH && showAdmin && (
          <ErrorBoundary title="Admin & Truth error" message="Unable to load Admin & Truth section.">
            <AdminTruthSection
              axiosConfig={axiosConfig}
              user={user}
              actionLoading={actionLoading}
              adminApiHealth={adminApiHealth}
              adminBots={adminBots}
              adminUsers={adminUsers}
              aiTaskLoading={aiTaskLoading}
              allUsers={allUsers}
              bodyguardStatus={bodyguardStatus}
              bots={bots}
              clearUserEmergencyOverride={clearUserEmergencyOverride}
              emergencyOverrideStatus={emergencyOverrideStatus}
              filteredAdminBots={filteredAdminBots}
              formatDate={formatDate}
              handleBlockUser={handleBlockUser}
              handleChangeBotExchange={handleChangeBotExchange}
              handleChangeBotMode={handleChangeBotMode}
              handleChangePassword={handleChangePassword}
              handleDeleteUser={handleDeleteUser}
              handleDeleteUserAdmin={handleDeleteUserAdmin}
              handleEmailAllUsers={handleEmailAllUsers}
              handleForceLogout={handleForceLogout}
              handleMigrateApiKeys={handleMigrateApiKeys}
              handleResetPassword={handleResetPassword}
              handleToggleBlockUser={handleToggleBlockUser}
              handleToggleBotPause={handleToggleBotPause}
              handleTriggerBodyguard={handleTriggerBodyguard}
              handleUserSelection={handleUserSelection}
              loadAdminUsers={loadAdminUsers}
              loadAdminBots={loadAdminBots}
              loadingBots={loadingBots}
              loadingUsers={loadingUsers}
              selectedBotId={selectedBotId}
              selectedUserId={selectedUserId}
              setActiveSection={setActiveSection}
              setChatMessages={setChatMessages}
              setSelectedBotId={setSelectedBotId}
              setSelectedUserId={setSelectedUserId}
              showNotification={showNotification}
              showSection={showSection}
              storageData={storageData}
              storageError={storageError}
              storageTotals={storageTotals}
              systemStats={systemStats}
              updateGlobalEmergencyOverride={updateGlobalEmergencyOverride}
              updateUserEmergencyOverride={updateUserEmergencyOverride}
            />
          </ErrorBoundary>
        )}

      </main>

      <ModalConfirm
        open={showEmergencyConfirm}
        onOpenChange={setShowEmergencyConfirm}
        title="Confirm Emergency Stop"
        description="Immediately halts all bots and trading activity across the system. Resume only when safe."
        confirmLabel="Activate Emergency Stop"
        confirmVariant="error"
        onConfirm={executeEmergencyStop}
      />

      {/* Bot Promotion Modal */}
      {showPromotionModal && eligibleBots.length > 0 && (
        <div className="modal-overlay" onClick={() => setShowPromotionModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>🎉 Bots Ready for Live Trading!</h2>
            <p style={{marginBottom: '20px'}}>
              {eligibleBots.length} bot(s) have completed their 7-day paper trading period and are eligible for live trading.
            </p>
            <div style={{marginBottom: '20px', textAlign: 'left', background: '#1a1a2e', padding: '15px', borderRadius: '8px'}}>
              <h3 style={{marginBottom: '10px', fontSize: '16px'}}>Eligible Bots:</h3>
              {eligibleBots.map(bot => (
                <div key={bot.id} style={{padding: '8px 0', borderBottom: '1px solid #333'}}>
                  <strong>{bot.name}</strong> - Capital: R{safeToFixed(bot.current_capital, 2)}, Profit: R{safeToFixed(bot.profit, 2)}
                </div>
              ))}
            </div>
            <div style={{marginBottom: '20px', textAlign: 'left', background: '#2a2a3e', padding: '15px', borderRadius: '8px'}}>
              <h3 style={{marginBottom: '10px', fontSize: '16px', color: 'var(--accent2)'}}>⚠️ Important Questions:</h3>
              <ol style={{paddingLeft: '20px'}}>
                <li style={{marginBottom: '8px'}}>Have you funded your LUNO wallet with real ZAR?</li>
                <li style={{marginBottom: '8px'}}>Do you want to use these paper-trained bots for live trading?</li>
                <li>Are you ready to trade with real money?</li>
              </ol>
            </div>
            <div style={{display: 'flex', gap: '10px', justifyContent: 'center'}}>
              <button
                className="btn-primary"
                onClick={() => confirmLiveSwitch(true, true)}
                style={{background: 'var(--success)', color: '#000', padding: '12px 24px'}}
              >
                ✅ Yes, I've Funded LUNO - Switch to Live!
              </button>
              <button
                className="btn-danger"
                onClick={() => {
                  setShowPromotionModal(false);
                  toast.info('Please fund your LUNO wallet before enabling live trading');
                }}
                style={{padding: '12px 24px'}}
              >
                ❌ Not Yet - Keep Paper Trading
              </button>
            </div>
          </div>
        </div>
      )}
      <SiteFooter />
    </div>
  );
}
