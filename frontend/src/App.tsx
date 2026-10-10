import { useEffect, useState } from "react";
import { login } from "./api";
import type { AuthState } from "./types";
import { DashboardLayout, type NavId } from "./layout/DashboardLayout";
import { HomePage } from "./pages/HomePage";
import { AssistantPage } from "./pages/AssistantPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { SettingsPage } from "./pages/SettingsPage";
import { TodosPage } from "./pages/TodosPage";

const AUTH_KEY = "aether_auth";

function loadAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(() => loadAuth());
  const [nav, setNav] = useState<NavId>("home");
  const [authMode, setAuthMode] = useState("local");
  const [loginForm, setLoginForm] = useState({
    username: "analyst@aether.bank",
    password: "password123",
  });
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1"}/config`)
      .then((r) => r.json())
      .then((c) => setAuthMode(c.auth_mode || "local"))
      .catch(() => undefined);
  }, []);

  const persistAuth = (a: AuthState | null) => {
    setAuth(a);
    if (a) localStorage.setItem(AUTH_KEY, JSON.stringify(a));
    else localStorage.removeItem(AUTH_KEY);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setLoggingIn(true);
    try {
      const data = await login(loginForm.username, loginForm.password);
      persistAuth({
        token: data.access_token,
        username: data.username,
        role: data.role as AuthState["role"],
      });
      setNav("home");
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoggingIn(false);
    }
  };

  if (!auth) {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={handleLogin}>
          <h1>
            <span>Aether</span> Bank
          </h1>
          <p className="sub">Enterprise platform — sign in to continue</p>
          {loginError && <div className="login-error">{loginError}</div>}
          <label htmlFor="user">Username</label>
          <input
            id="user"
            value={loginForm.username}
            onChange={(e) => setLoginForm((f) => ({ ...f, username: e.target.value }))}
          />
          <label htmlFor="pass">Password</label>
          <input
            id="pass"
            type="password"
            value={loginForm.password}
            onChange={(e) => setLoginForm((f) => ({ ...f, password: e.target.value }))}
          />
          <button className="primary" type="submit" disabled={loggingIn}>
            {loggingIn ? "Signing in…" : "Sign in"}
          </button>
          <p className="demo-hints">
            Local auth: analyst@aether.bank / password123
            <br />
            Keycloak mode: use realm users when AUTH_MODE=keycloak
          </p>
        </form>
      </div>
    );
  }

  return (
    <DashboardLayout
      active={nav}
      onNavigate={setNav}
      username={auth.username}
      role={auth.role}
      onLogout={() => persistAuth(null)}
    >
      {nav === "home" && (
        <HomePage username={auth.username} onOpenAssistant={() => setNav("assistant")} />
      )}
      {nav === "assistant" && <AssistantPage auth={auth} />}
      {nav === "todos" && <TodosPage auth={auth} />}
      {nav === "knowledge" && <KnowledgePage />}
      {nav === "settings" && <SettingsPage authMode={authMode} />}
    </DashboardLayout>
  );
}
