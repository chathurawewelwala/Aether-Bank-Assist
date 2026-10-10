export type UserRole = "viewer" | "analyst" | "administrator";

export interface Citation {
  source: string;
  excerpt?: string;
  score?: number;
  document_type?: string;
  department?: string;
}

export interface ActivityEvent {
  node?: string;
  state?: string;
  message?: string;
  timestamp?: string;
  details?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  activity?: ActivityEvent[];
  /** True while agent is still running and answer is not final */
  isStreaming?: boolean;
  /** Human-in-the-loop: waiting for Approve / Reject */
  pendingApproval?: boolean;
  pendingTools?: string[];
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  serverSessionId: string | null;
  messages: ChatMessage[];
  updatedAt: number;
}

export interface AuthState {
  token: string;
  username: string;
  role: UserRole;
}
