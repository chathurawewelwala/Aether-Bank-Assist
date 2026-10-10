import { useCallback, useEffect, useState } from "react";
import type { AuthState } from "../types";
import {
  createTodo,
  deleteTodo,
  listTodos,
  updateTodo,
  type TodoItem,
} from "../api";

export function TodosPage({ auth }: { auth: AuthState }) {
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("medium");
  const [filter, setFilter] = useState<"all" | "open" | "done">("all");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const status = filter === "all" ? undefined : filter;
      const data = await listTodos(auth.token, status);
      setTodos(data.todos || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load to-dos");
    } finally {
      setLoading(false);
    }
  }, [auth.token, filter]);

  useEffect(() => {
    load();
  }, [load]);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    try {
      await createTodo(auth.token, { title: title.trim(), priority });
      setTitle("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleDone = async (t: TodoItem) => {
    setBusy(true);
    try {
      await updateTodo(auth.token, t.id, {
        status: t.status === "done" ? "open" : "done",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    setBusy(true);
    try {
      await deleteTodo(auth.token, id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>To-dos</h1>
        <p>
          Personal task list stored in PostgreSQL. You can also manage these via{" "}
          <strong>Aether Assistant</strong> (“Add a todo…”, “List my tasks”).
        </p>
      </header>

      <form className="todo-form" onSubmit={onAdd}>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs to be done?"
          disabled={busy}
        />
        <select value={priority} onChange={(e) => setPriority(e.target.value)} disabled={busy}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        <button type="submit" className="btn-primary" disabled={busy || !title.trim()}>
          Add
        </button>
      </form>

      <div className="todo-filters">
        {(["all", "open", "done"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={filter === f ? "filter active" : "filter"}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {error && <div className="login-error" style={{ marginBottom: "1rem" }}>{error}</div>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : todos.length === 0 ? (
        <div className="empty-state">
          <h3>No to-dos yet</h3>
          <p>Add one above, or ask the Assistant: “Add a todo to review the PayFlow runbook”.</p>
        </div>
      ) : (
        <ul className="todo-list">
          {todos.map((t) => (
            <li key={t.id} className={`todo-item ${t.status}`}>
              <button
                type="button"
                className="todo-check"
                title={t.status === "done" ? "Mark open" : "Mark done"}
                onClick={() => toggleDone(t)}
                disabled={busy}
              >
                {t.status === "done" ? "✓" : "○"}
              </button>
              <div className="todo-body">
                <div className="todo-title">{t.title}</div>
                {t.description && <div className="todo-desc">{t.description}</div>}
                <div className="todo-meta">
                  <span className={`prio ${t.priority}`}>{t.priority}</span>
                  <span>{t.status}</span>
                  {t.due_date && <span>due {t.due_date}</span>}
                </div>
              </div>
              <button type="button" className="btn-ghost" onClick={() => onDelete(t.id)} disabled={busy}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
