import PublicPageLayout from '../components/PublicPageLayout';

export default function Privacy() {
  return (
    <PublicPageLayout
      title="Privacy Policy"
      subtitle="Your credentials stay encrypted and within your control."
    >
      <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.6 }}>
        AmarktAI Crypto stores only the data required to operate your trading automations. API keys are encrypted
        before storage and are never shown in plaintext once saved. You can revoke any key at any time from the
        API Setup section.
      </p>
      <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.6 }}>
        Usage metrics are limited to operational telemetry that keeps the platform stable. We do not sell or
        share personal data.
      </p>
    </PublicPageLayout>
  );
}
