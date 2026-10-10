import type { ReactNode } from "react";

export type NavId = "home" | "assistant" | "todos" | "knowledge" | "settings";

const NAV: { id: NavId; label: string; icon: string }[] = [
  { id: "home", label: "Overview", icon: "▣" },
  { id: "assistant", label: "Aether Assistant", icon: "◈" },
  { id: "todos", label: "To-dos", icon: "☑" },
  { id: "knowledge", label: "Knowledge", icon: "▤" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

export function DashboardLayout({
  active,
  onNavigate,
  username,
  role,
  onLogout,
  children,
}: {
  active: NavId;
  onNavigate: (id: NavId) => void;
  username: string;
  role: string;
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <div className="dash">
      <aside className="dash-nav">
        <div className="dash-brand">
          <span className="logo">A</span>
          <div>
            <strong>Aether Bank</strong>
            <small>Enterprise Platform</small>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={active === item.id ? "nav-item active" : "nav-item"}
              onClick={() => onNavigate(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="dash-user">
          <div>
            <div className="u-name">{username}</div>
            <span className="role-pill">{role}</span>
          </div>
          <button type="button" className="btn-ghost" onClick={onLogout}>
            Log out
          </button>
        </div>
      </aside>
      <main className="dash-main">{children}</main>
    </div>
  );
}
