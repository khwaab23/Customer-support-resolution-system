import { getCsrfHeaders } from "./auth";
import { apiRequest } from "./client";

export type ChatMessage = { message_id: string; sender_role: "CUSTOMER" | "ASSISTANT" | "SYSTEM_EVENT"; message_text: string; created_at: string; metadata?: Record<string, unknown> };
export type ChatConversation = { conversation_id: string; selected_order_id: string | null; linked_ticket_id: string | null; status: string; version: number; created_at: string; updated_at: string; review_status?: string | null };
export type ChatDetail = ChatConversation & { messages: ChatMessage[] };
type Turn = { conversation: ChatConversation; customer_message: ChatMessage; assistant_message: ChatMessage | null; idempotent_replay: boolean };

export async function createConversation(selectedOrderId?: string): Promise<ChatConversation> {
  const headers = await getCsrfHeaders();
  return apiRequest("/v1/customer/chat/conversations", { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify({ selected_order_id: selectedOrderId }) });
}
export const getConversation = (id: string): Promise<ChatDetail> => apiRequest(`/v1/customer/chat/conversations/${encodeURIComponent(id)}`);
export async function selectChatOrder(id: string, orderId: string): Promise<ChatConversation> {
  const headers = await getCsrfHeaders();
  return apiRequest(`/v1/customer/chat/conversations/${encodeURIComponent(id)}/select-order`, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify({ order_id: orderId }) });
}
export async function sendChatMessage(id: string, message: string, requestId: string): Promise<Turn> {
  const headers = await getCsrfHeaders();
  return apiRequest(`/v1/customer/chat/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify({ message, client_request_id: requestId }) });
}
