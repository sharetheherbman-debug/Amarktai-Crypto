import PublicPageLayout from '../components/PublicPageLayout';

export default function Terms() {
  return (
    <PublicPageLayout
      title="Terms of Use"
      subtitle="Please review the terms for personal use of Amarktai Network."
    >
      <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.6 }}>
        Amarktai Network is provided for personal, educational, and research purposes. You are responsible for
        safeguarding your credentials and confirming the accuracy of any automated actions before enabling live
        trading. The platform communicates directly with your configured exchanges using the credentials you
        provide.
      </p>
      <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.6 }}>
        By using this application, you agree to monitor system status, maintain secure access, and comply with
        all relevant regulations in your jurisdiction.
      </p>
    </PublicPageLayout>
  );
}
