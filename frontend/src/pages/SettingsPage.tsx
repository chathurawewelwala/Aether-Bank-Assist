export function SettingsPage({ authMode }: { authMode: string }) {
  return (
    <div className="page">
      <header className="page-header">
        <h1>Settings</h1>
        <p>Environment and identity configuration (read-only in this POC).</p>
      </header>
      <div className="card">
        <dl className="kv">
          <dt>Auth mode</dt>
          <dd>{authMode}</dd>
          <dt>Identity</dt>
          <dd>Local JWT or Keycloak realm <code>aether</code></dd>
          <dt>Session store</dt>
          <dd>Redis (with in-memory fallback)</dd>
          <dt>Persistence</dt>
          <dd>PostgreSQL</dd>
        </dl>
      </div>
    </div>
  );
}
