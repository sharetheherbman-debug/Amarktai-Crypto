import { useState } from 'react';
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
import useDashboardState from '../hooks/useDashboardState';
import Badge from '@/ui/components/Badge';
import ModalConfirm from '@/ui/components/ModalConfirm';
import WelcomeSection from './dashboard/sections/WelcomeSection';
import OverviewSection from './dashboard/sections/OverviewSection';
import ProfileSection from './dashboard/sections/ProfileSection';
import SystemModeSection from './dashboard/sections/SystemModeSection';
import LiveTradesSection from './dashboard/sections/LiveTradesSection';
import CountdownSection from './dashboard/sections/CountdownSection';
import WalletHubSection from './dashboard/sections/WalletHubSection';
import ApiSetupSection from './dashboard/sections/ApiSetupSection';
import BotManagementSection from './dashboard/sections/BotManagementSection';
import MetricsWithTabsSection from './dashboard/sections/MetricsWithTabsSection';
import PerformanceSection from './dashboard/sections/PerformanceSection';
import AdminTruthSection from './dashboard/sections/AdminTruthSection';
import BotFleetSection from './dashboard/sections/BotFleetSection';
import BotRadarSection from './dashboard/sections/BotRadarSection';
import GrowthEngineSection from './dashboard/sections/GrowthEngineSection';
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
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

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
    autopilotGrowthStatus,
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
    handleCreateScalperBot,
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
    handlePauseBot,
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
    handleRestartBot,
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


  return (
    <div className="app">
      {/* Sidebar - Desktop */}
      {!isMobile && (
        <aside className="sidebar">
          <img
            src="/assets/logo.png"
            className="logo sidebar-logo"
            alt="Amarktai Crypto"
            onClick={() => showSection(NAV.OVERVIEW)}
            style={{ cursor: 'pointer' }}
          />
          <nav className="nav" key={`nav-${showAdmin}`}>
            <a href="#" className={activeSection === NAV.WELCOME ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.WELCOME); }}>{NAV_LABELS[NAV.WELCOME]}</a>
            <a href="#" className={activeSection === NAV.API_SETUP ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.API_SETUP); }}>{NAV_LABELS[NAV.API_SETUP]}</a>
            <a href="#" className={activeSection === NAV.BOT_MANAGEMENT ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.BOT_MANAGEMENT); }}>{NAV_LABELS[NAV.BOT_MANAGEMENT]}</a>
            <a href="#" className={activeSection === NAV.BOT_FLEET ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.BOT_FLEET); }}>{NAV_LABELS[NAV.BOT_FLEET]}</a>
            <a href="#" className={activeSection === NAV.BOT_RADAR ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.BOT_RADAR); }}>{NAV_LABELS[NAV.BOT_RADAR]}</a>
            <a href="#" className={activeSection === NAV.GROWTH_ENGINE ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.GROWTH_ENGINE); }}>{NAV_LABELS[NAV.GROWTH_ENGINE]}</a>
            <a href="#" className={activeSection === NAV.SYSTEM_MODE ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.SYSTEM_MODE); }}>{NAV_LABELS[NAV.SYSTEM_MODE]}</a>
            <a href="#" className={activeSection === NAV.ANALYTICS_METRICS ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.ANALYTICS_METRICS); }}>{NAV_LABELS[NAV.ANALYTICS_METRICS]}</a>
            <a href="#" className={activeSection === NAV.PROFITS_PERFORMANCE ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.PROFITS_PERFORMANCE); }}>{NAV_LABELS[NAV.PROFITS_PERFORMANCE]}</a>
            <a href="#" className={activeSection === NAV.LIVE_TRADES ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.LIVE_TRADES); }}>{NAV_LABELS[NAV.LIVE_TRADES]}</a>
            <a href="#" className={activeSection === NAV.COUNTDOWN ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.COUNTDOWN); }}>{NAV_LABELS[NAV.COUNTDOWN]}</a>
            <a href="#" className={activeSection === NAV.WALLET_HUB ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.WALLET_HUB); }}>{NAV_LABELS[NAV.WALLET_HUB]}</a>
            <a href="#" className={activeSection === NAV.PROFILE ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.PROFILE); }}>{NAV_LABELS[NAV.PROFILE]}</a>
            {showAdmin && (
              <a href="#" className={activeSection === NAV.HIDDEN_ADMIN ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(NAV.HIDDEN_ADMIN); }}>{NAV_LABELS[NAV.HIDDEN_ADMIN]}</a>
            )}
          </nav>
        </aside>
      )}

      {/* Topbar - Desktop */}
      {!isMobile && (
        <header className="topbar">
            <div className="topbar-brand">
              <div className="topbar-title">Amarktai Crypto</div>
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
          <button className="mobile-hamburger" onClick={() => setMobileDrawerOpen(true)}>☰</button>
          <button className="mobile-logo-btn" onClick={() => { showSection(NAV.OVERVIEW); setMobileDrawerOpen(false); }}>
            <img src="/assets/logo.png" className="mobile-logo" alt="Amarktai Crypto" />
          </button>
          <button className="logout-btn" onClick={handleLogout} style={{fontSize:'0.8rem',padding:'6px 10px'}}>Logout</button>
        </div>
      )}

      {/* Mobile Drawer */}
      {isMobile && (
        <>
          <div className={`mobile-drawer-overlay ${mobileDrawerOpen ? 'open' : ''}`} onClick={() => setMobileDrawerOpen(false)} />
          <div className={`mobile-drawer ${mobileDrawerOpen ? 'open' : ''}`}>
            <img src="/assets/logo.png" className="logo sidebar-logo" alt="Amarktai Crypto" onClick={() => { showSection(NAV.OVERVIEW); setMobileDrawerOpen(false); }} style={{cursor:'pointer',margin:'0 auto 16px'}} />
            <nav className="nav">
              {Object.entries(NAV_LABELS).map(([key, label]) => {
                if (key === NAV.HIDDEN_ADMIN && !showAdmin) return null;
                return (
                  <a key={key} href="#" className={activeSection === key ? 'active' : ''} onClick={(e) => { e.preventDefault(); showSection(key); setMobileDrawerOpen(false); }}>{label}</a>
                );
              })}
            </nav>
          </div>
        </>
      )}

      {/* Main Content */}
      <main className="main"> 
        {activeSection === NAV.OVERVIEW && (
          <ErrorBoundary title="Overview error" message="Unable to load Overview.">
            <OverviewSection
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
              user={user}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.WELCOME && (
          <ErrorBoundary title="Welcome error" message="Unable to load Welcome section.">
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
          </ErrorBoundary>
        )}
        {activeSection === NAV.API_SETUP && (
          <ErrorBoundary title="API Setup error" message="Unable to load API Setup section.">
            <ApiSetupSection />
          </ErrorBoundary>
        )}
        {activeSection === NAV.BOT_MANAGEMENT && (
          <ErrorBoundary title="Bot Management error" message="Unable to load Bot Management section.">
            <BotManagementSection
              axiosConfig={axiosConfig}
              botManagementTab={botManagementTab}
              handleCreateBot={handleCreateBot}
              handleCreateScalperBot={handleCreateScalperBot}
              handleCreateUAgent={handleCreateUAgent}
              setBotManagementTab={setBotManagementTab}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.BOT_FLEET && (
          <ErrorBoundary title="Bot Fleet error" message="Unable to load Bot Fleet section.">
            <BotFleetSection
              bots={bots}
              formatDate={formatDate}
              handleDeleteBot={handleDeleteBot}
              handleResumeBot={handleResumeBot}
              handleStartBot={handleStartBot}
              handlePauseBot={handlePauseBot}
              handleRestartBot={handleRestartBot}
              handleToggleBotMode={handleToggleBotMode}
              botControlLoading={botControlLoading}
              selectedBotDetailId={selectedBotDetailId}
              setSelectedBotDetailId={setSelectedBotDetailId}
              botDetailTab={botDetailTab}
              setBotDetailTab={setBotDetailTab}
              botStatusFilter={botStatusFilter}
              setBotStatusFilter={setBotStatusFilter}
              platformFilter={platformFilter}
              setPlatformFilter={setPlatformFilter}
              editingBotId={editingBotId}
              setEditingBotId={setEditingBotId}
              editingBotName={editingBotName}
              setEditingBotName={setEditingBotName}
              handleRenameBotSubmit={handleRenameBotSubmit}
              axiosConfig={axiosConfig}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.BOT_RADAR && (
          <ErrorBoundary title="Bot Radar error" message="Unable to load Bot Radar section.">
            <BotRadarSection axiosConfig={axiosConfig} />
          </ErrorBoundary>
        )}
        {activeSection === NAV.GROWTH_ENGINE && (
          <ErrorBoundary title="Growth Engine error" message="Unable to load Growth Engine section.">
            <GrowthEngineSection
              autopilotGrowthStatus={autopilotGrowthStatus}
              autopilotReinvestStatus={autopilotReinvestStatus}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.SYSTEM_MODE && (
          <ErrorBoundary title="System Mode error" message="Unable to load System Mode section.">
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
          </ErrorBoundary>
        )}
        {activeSection === NAV.ANALYTICS_METRICS && (
          <ErrorBoundary title="Analytics & Metrics error" message="Unable to load Analytics & Metrics section.">
            <MetricsWithTabsSection
              metrics={metrics}
              metricsTab={metricsTab}
              setMetricsTab={setMetricsTab}
              axiosConfig={axiosConfig}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.PROFITS_PERFORMANCE && (
          <ErrorBoundary title="Profits & Performance error" message="Unable to load Profits & Performance section.">
            <PerformanceSection
              axiosConfig={axiosConfig}
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
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.LIVE_TRADES && (
          <ErrorBoundary title="Live Trades error" message="Unable to load Live Trades section.">
            <LiveTradesSection
              recentTrades={recentTrades}
              realtimeConnected={realtimeConnected}
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
        {activeSection === NAV.COUNTDOWN && (
          <ErrorBoundary title="Countdown error" message="Unable to load Countdown section.">
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
        {activeSection === NAV.WALLET_HUB && (
          <ErrorBoundary title="Wallet Hub error" message="Unable to load Wallet Hub section.">
            <WalletHubSection
              balances={balances}
              systemModes={systemModes}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.PROFILE && (
          <ErrorBoundary title="Profile error" message="Unable to load Profile section.">
            <ProfileSection
              user={user}
              bots={bots}
              formatDate={formatDate}
              profileData={profileData}
              handleProfileChange={handleProfileChange}
              handleProfileSave={handleProfileSave}
              handleEmergencyStop={handleEmergencyStop}
            />
          </ErrorBoundary>
        )}
        {activeSection === NAV.HIDDEN_ADMIN && showAdmin && (
          <ErrorBoundary title="Admin error" message="Unable to load Admin section.">
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
