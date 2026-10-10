import type { ActivityEvent, Citation } from "./types";

/**
 * Prefer direct backend URL so SSE is not buffered by the Vite proxy.
 * Override with VITE_API_BASE if needed (e.g. "/api/v1" behind a reverse proxy).
 */
const API_BASE =
  import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";

export interface LoginResult {
  access_token: string;
  role: string;
  username: string;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Login failed");
  }
  return res.json();
}

export interface StreamHandlers {
  onStatus?: (payload: { state?: string; node?: string; session_id?: string }) => void;
  onActivity?: (ev: ActivityEvent) => void;
  onAnswer?: (payload: {
    session_id?: string;
    content: string;
    citations?: Citation[];
    error?: string;
    pending_approval?: boolean;
    pending_tools?: string[];
  }) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

function dispatchSseEvent(event: string, payload: Record<string, unknown>, handlers: StreamHandlers) {
  const name = (event || "message").toLowerCase();

  // Explicit event names from backend
  if (name === "activity") {
    handlers.onActivity?.(payload as ActivityEvent);
    return;
  }
  if (name === "status") {
    handlers.onStatus?.(payload as { state?: string; node?: string; session_id?: string });
    return;
  }
  if (name === "answer") {
    handlers.onAnswer?.(payload as {
      session_id?: string;
      content: string;
      citations?: Citation[];
      error?: string;
    });
    return;
  }
  if (name === "done") {
    handlers.onDone?.();
    return;
  }

  // Infer from payload shape (some proxies strip the event: field)
  if (typeof payload.content === "string" && (payload.session_id || payload.citations)) {
    handlers.onAnswer?.(payload as {
      session_id?: string;
      content: string;
      citations?: Citation[];
      error?: string;
    });
    return;
  }
  if (payload.node || payload.message) {
    handlers.onActivity?.(payload as ActivityEvent);
    return;
  }
  if (payload.state || payload.session_id) {
    handlers.onStatus?.(payload as { state?: string; node?: string; session_id?: string });
  }
}

/** Parse one SSE block (event + data lines) into { event, data } */
function parseSseBlock(block: string): { event: string; data: string } | null {
  const normalized = block.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!normalized) return null;

  let event = "message";
  const dataLines: string[] = [];

  for (const rawLine of normalized.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) continue; // comment / heartbeat
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/** Stream agent activity + final answer via SSE over fetch */
export async function streamChat(
  token: string,
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, session_id: sessionId, stream: true }),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail || err);
    throw new Error(detail || `HTTP ${res.status}`);
  }

  if (!res.body) {
    await nonStreamChat(token, message, sessionId, handlers);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let gotAnswer = false;
  let gotActivity = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // Normalize newlines; SSE frames end with a blank line
    buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const parsed = parseSseBlock(part);
      if (!parsed) continue;

      try {
        const payload = JSON.parse(parsed.data) as Record<string, unknown>;
        const evName = parsed.event.toLowerCase();

        if (evName === "answer" || (typeof payload.content === "string" && payload.citations !== undefined)) {
          gotAnswer = true;
        }
        if (evName === "activity" || payload.node || payload.message) {
          gotActivity = true;
        }

        dispatchSseEvent(parsed.event, payload, handlers);
      } catch (e) {
        console.warn("[aether SSE] parse failed", parsed.data, e);
      }
    }
  }

  // Flush trailing buffer (last frame without trailing \n\n)
  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer);
    if (parsed) {
      try {
        const payload = JSON.parse(parsed.data) as Record<string, unknown>;
        if (parsed.event.toLowerCase() === "answer") gotAnswer = true;
        dispatchSseEvent(parsed.event, payload, handlers);
      } catch {
        /* ignore */
      }
    }
  }

  if (!gotAnswer) {
    console.warn("[aether SSE] no answer event; falling back to /chat", { gotActivity });
    await nonStreamChat(token, message, sessionId, handlers);
  }
}

async function nonStreamChat(
  token: string,
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, session_id: sessionId, stream: false }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Chat failed");
  }
  const data = await res.json();
  for (const a of data.agent_trace || []) handlers.onActivity?.(a);
  handlers.onAnswer?.({
    session_id: data.session_id,
    content: data.message?.content || "",
    citations: data.message?.citations || [],
  });
  handlers.onDone?.();
}


export async function approveChat(
  token: string,
  sessionId: string,
  approved: boolean
): Promise<{
  content: string;
  citations?: Citation[];
  agent_trace?: ActivityEvent[];
  session_id?: string;
}> {
  const res = await fetch(`${API_BASE}/chat/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ session_id: sessionId, approved }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Approval failed");
  }
  return res.json();
}


export interface TodoItem {
  id: string;
  username?: string;
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  due_date?: string | null;
  created_at?: string;
  updated_at?: string;
}

export async function listTodos(
  token: string,
  status?: string
): Promise<{ todos: TodoItem[]; count: number }> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`${API_BASE}/todos${q}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to list to-dos");
  return res.json();
}

export async function createTodo(
  token: string,
  body: { title: string; description?: string; priority?: string; due_date?: string }
): Promise<TodoItem> {
  const res = await fetch(`${API_BASE}/todos`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Create failed");
  }
  return res.json();
}

export async function updateTodo(
  token: string,
  id: string,
  body: Partial<{ title: string; description: string; status: string; priority: string; due_date: string }>
): Promise<TodoItem> {
  const res = await fetch(`${API_BASE}/todos/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Update failed");
  return res.json();
}

export async function deleteTodo(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/todos/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Delete failed");
}
