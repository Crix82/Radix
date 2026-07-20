import type { Citation } from "./chat";
import { api } from "./client";

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  user_id: number;
  user_email: string | null;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  refusal: boolean;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export function listConversations(): Promise<Conversation[]> {
  return api<Conversation[]>("/conversations");
}

export function getConversation(id: number): Promise<ConversationDetail> {
  return api<ConversationDetail>(`/conversations/${id}`);
}

export function deleteConversation(id: number): Promise<void> {
  return api<void>(`/conversations/${id}`, { method: "DELETE" });
}
