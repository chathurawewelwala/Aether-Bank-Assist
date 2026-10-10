import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { approveChat, streamChat } from "../api";
import type { ActivityEvent, AuthState, ChatMessage, Conversation } from "../types";

const CONV_KEY = "aether_conversations";

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CONV_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function titleFromMessage(text: string) {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 42 ? t.slice(0, 42) + "…" : t || "New chat";
}

export function AssistantPage({ auth }: { auth: AuthState }) {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const active = useMemo(
    () => conversations.find((c) => c.id === activeId) || null,
    [conversations, activeId]
  );

  useEffect(() => {
    localStorage.setItem(CONV_KEY, JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages, busy]);

  const updateConv = useCallback((id: string, fn: (c: Conversation) => Conversation) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? fn(c) : c)));
  }, []);

  const newChat = () => {
    const conv: Conversation = {
      id: uid(),
      title: "New chat",
      serverSessionId: null,
      messages: [],
      updatedAt: Date.now(),
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
  };

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    let convId = activeId;
    if (!convId) {
      const conv: Conversation = {
        id: uid(),
        title: titleFromMessage(text),
        serverSessionId: null,
        messages: [],
        updatedAt: Date.now(),
      };
      setConversations((prev) => [conv, ...prev]);
      convId = conv.id;
      setActiveId(conv.id);
    }

    const userMsg: ChatMessage = {
      id: uid(),
      role: "user",
      content: text.trim(),
      createdAt: Date.now(),
    };
    const streamId = uid();
    const streamMsg: ChatMessage = {
      id: streamId,
      role: "assistant",
      content: "",
      activity: [],
      isStreaming: true,
      createdAt: Date.now(),
    };

    updateConv(convId, (c) => ({
      ...c,
      title: c.messages.length === 0 ? titleFromMessage(text) : c.title,
      messages: [...c.messages, userMsg, streamMsg],
      updatedAt: Date.now(),
    }));
    setInput("");
    setBusy(true);

    const activities: ActivityEvent[] = [];
    try {
      const serverSession =
        conversations.find((c) => c.id === convId)?.serverSessionId ?? null;

      await streamChat(auth.token, text.trim(), serverSession, {
        onStatus: (p) => {
          if (p.session_id) {
            updateConv(convId!, (c) => ({
              ...c,
              serverSessionId: p.session_id || c.serverSessionId,
            }));
          }
          if (p.state) {
            activities.push({
              node: p.node || "system",
              state: "thinking",
              message: p.node ? `${p.state} → ${p.node}` : p.state,
            });
            updateConv(convId!, (c) => ({
              ...c,
              messages: c.messages.map((m) =>
                m.id === streamId ? { ...m, activity: [...activities] } : m
              ),
            }));
          }
        },
        onActivity: (ev) => {
          activities.push(ev);
          updateConv(convId!, (c) => ({
            ...c,
            messages: c.messages.map((m) =>
              m.id === streamId ? { ...m, activity: [...activities] } : m
            ),
          }));
        },
        onAnswer: (payload) => {
          if (payload.session_id) {
            updateConv(convId!, (c) => ({
              ...c,
              serverSessionId: payload.session_id || c.serverSessionId,
            }));
          }
          updateConv(convId!, (c) => ({
            ...c,
            messages: c.messages.map((m) =>
              m.id === streamId
                ? {
                    ...m,
                    content: payload.content || "(empty response)",
                    citations: payload.citations || [],
                    activity: [],
                    isStreaming: false,
                    pendingApproval: !!payload.pending_approval,
                    pendingTools: payload.pending_tools || [],
                  }
                : m
            ),
            updatedAt: Date.now(),
          }));
        },
        onDone: () => {
          updateConv(convId!, (c) => ({
            ...c,
            messages: c.messages.map((m) =>
              m.id === streamId
                ? { ...m, isStreaming: false, activity: m.content ? [] : m.activity }
                : m
            ),
          }));
        },
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      updateConv(convId!, (c) => ({
        ...c,
        messages: c.messages.map((m) =>
          m.id === streamId
            ? {
                ...m,
                content: `Error: ${msg}`,
                isStreaming: false,
                activity: [],
              }
            : m
        ),
      }));
    } finally {
      setBusy(false);
    }
  };

  const resolveApproval = async (messageId: string, approved: boolean) => {
    if (!active?.serverSessionId || busy) return;
    setBusy(true);
    try {
      const result = await approveChat(auth.token, active.serverSessionId, approved);
      updateConv(active.id, (c) => ({
        ...c,
        messages: [
          ...c.messages.map((m) =>
            m.id === messageId ? { ...m, pendingApproval: false } : m
          ),
          {
            id: uid(),
            role: "assistant",
            content: result.content || (approved ? "Approved." : "Rejected."),
            citations: result.citations || [],
            isStreaming: false,
            pendingApproval: false,
            createdAt: Date.now(),
          },
        ],
        updatedAt: Date.now(),
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      updateConv(active.id, (c) => ({
        ...c,
        messages: [
          ...c.messages,
          { id: uid(), role: "assistant", content: `Approval error: ${msg}`, createdAt: Date.now() },
        ],
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="assistant-layout">
      <aside className="chat-sessions">
        <div className="chat-sessions-hd">
          <h2>Chats</h2>
          <button type="button" className="btn-new" onClick={newChat}>
            + New
          </button>
        </div>
        <div className="session-list">
          {conversations.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`session-item ${c.id === activeId ? "active" : ""}`}
              onClick={() => setActiveId(c.id)}
            >
              <div className="title">{c.title}</div>
              <div className="meta">{new Date(c.updatedAt).toLocaleString()}</div>
            </button>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        <div className="chat-toolbar">
          <h3>{active?.title || "Aether Assistant"}</h3>
        </div>

        {!active || active.messages.length === 0 ? (
          <div className="empty-state">
            <h3>How can I help?</h3>
            <p>Policies, incidents, runbooks — or HITL employee lookups.</p>
          </div>
        ) : (
          <div className="messages">
            {active.messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                busy={busy}
                onApprove={m.pendingApproval ? () => resolveApproval(m.id, true) : undefined}
                onReject={m.pendingApproval ? () => resolveApproval(m.id, false) : undefined}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        <div className="examples">
          {[
            "Summarize all outage reports related to payment failures during the last year and identify recurring root causes.",
            "What is the recovery procedure for connection pool exhaustion on PayFlow?",
            "Who is on the Payments Platform team?",
          ].map((q) => (
            <button key={q} type="button" disabled={busy} onClick={() => send(q)}>
              {q.length > 48 ? q.slice(0, 48) + "…" : q}
            </button>
          ))}
        </div>

        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Aether Assistant…"
            rows={1}
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          <button type="button" className="send" disabled={busy || !input.trim()} onClick={() => send(input)}>
            {busy ? "…" : "Send"}
          </button>
        </div>
      </section>
    </div>
  );
}

function MessageBubble({
  message,
  onApprove,
  onReject,
  busy,
}: {
  message: ChatMessage;
  onApprove?: () => void;
  onReject?: () => void;
  busy?: boolean;
}) {
  const m = message;
  if (m.role === "user") return <div className="msg user">{m.content}</div>;

  if (m.isStreaming) {
    const steps = m.activity || [];
    return (
      <div className="msg assistant streaming">
        <div className="activity-live">
          <div className="label">
            <span className="pulse" />
            Agent steps
          </div>
          {steps.length === 0 ? (
            <div className="activity-step">
              <span className="node-tag">system</span>
              <span className="state-tag thinking">thinking</span>
              <span>Starting…</span>
            </div>
          ) : (
            steps.map((a, i) => (
              <div className={`activity-step ${i === steps.length - 1 ? "step-latest" : "step-done"}`} key={i}>
                <span className="node-tag">{a.node || "node"}</span>
                {a.state && <span className={`state-tag ${String(a.state).toLowerCase()}`}>{a.state}</span>}
                <span>{a.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`msg assistant ${m.pendingApproval ? "pending-hitl" : ""}`}>
      {m.content && <div>{m.content}</div>}
      {m.pendingApproval && (
        <div className="hitl-actions">
          <p className="hitl-label">Human-in-the-loop — confirm to continue</p>
          {m.pendingTools && m.pendingTools.length > 0 && (
            <p className="hitl-tools">Tools: {m.pendingTools.join(", ")}</p>
          )}
          <div className="hitl-buttons">
            <button type="button" className="btn-approve" disabled={busy} onClick={onApprove}>
              Approve
            </button>
            <button type="button" className="btn-reject" disabled={busy} onClick={onReject}>
              Reject
            </button>
          </div>
        </div>
      )}
      {m.citations && m.citations.length > 0 && (
        <details className="citations">
          <summary>{m.citations.length} citation(s)</summary>
          <ul>
            {m.citations.map((c, i) => (
              <li key={i}>
                {c.source}
                {typeof c.score === "number" ? ` (score: ${c.score.toFixed(2)})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
