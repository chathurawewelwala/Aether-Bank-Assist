export function HomePage({ username, onOpenAssistant }: { username: string; onOpenAssistant: () => void }) {
  return (
    <div className="page">
      <header className="page-header">
        <h1>Overview</h1>
        <p>Welcome back, {username}</p>
      </header>
      <div className="card-grid">
        <div className="card">
          <h3>Aether Assistant</h3>
          <p>Multi-agent RAG assistant for policies, incidents, and runbooks.</p>
          <button type="button" className="btn-primary" onClick={onOpenAssistant}>
            Open Assistant
          </button>
        </div>
        <div className="card">
          <h3>Platform health</h3>
          <ul className="stat-list">
            <li>API · operational</li>
            <li>Retrieval · hybrid BM25 + dense</li>
            <li>Auth · local / Keycloak</li>
            <li>Data · Postgres + Redis</li>
          </ul>
        </div>
        <div className="card">
          <h3>Quick tips</h3>
          <p>Use HITL questions (employee directory) to exercise human approval.</p>
          <p>Ask for recurring payment root causes to trigger the RLM research path.</p>
        </div>
      </div>
    </div>
  );
}
