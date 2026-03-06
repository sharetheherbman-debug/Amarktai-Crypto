import SectionHeader from '@/ui/components/SectionHeader';
import ProfileSection from './ProfileSection';
import SystemModeSection from './SystemModeSection';
import ApiSetupSection from './ApiSetupSection';

export default function ProfileControlsSection({
  user,
  bots,
  formatDate,
  profileData,
  handleProfileChange,
  handleProfileSave,
  handleEmergencyStop,
  handlePaperReset,
  handleRiskProfileChange,
  paperResetChecking,
  paperResetError,
  paperResetLoading,
  paperResetPassword,
  paperResetValid,
  riskProfile,
  setPaperResetError,
  setPaperResetPassword,
  setPaperResetValid,
  setShowPaperResetModal,
  showPaperResetModal,
  systemModes,
  toggleSystemMode,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="👤 Profile & Controls"
          subtitle="Account settings, system modes, risk profile, and emergency controls."
        />
      </div>
      <ProfileSection
        user={user}
        bots={bots}
        formatDate={formatDate}
        profileData={profileData}
        handleProfileChange={handleProfileChange}
        handleProfileSave={handleProfileSave}
        handleEmergencyStop={handleEmergencyStop}
      />
      <div style={{ marginTop: '16px' }}>
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
      </div>
      <div style={{ marginTop: '16px' }}>
        <ApiSetupSection />
      </div>
    </section>
  );
}
