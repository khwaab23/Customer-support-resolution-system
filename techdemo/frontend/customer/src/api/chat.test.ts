import { afterEach, describe, expect, it, vi } from "vitest";

import { createConversation, sendChatMessage } from "./chat";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("chat API", () => {
  afterEach(() => { fetchMock.mockReset(); document.cookie = "techdemo_csrf=; Max-Age=0; Path=/"; });

  it("creates a conversation with CSRF and cookie credentials", async () => {
    document.cookie = "techdemo_csrf=chat-token; Path=/";
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(jsonResponse({ conversation_id: "c", selected_order_id: null, linked_ticket_id: null, status: "OPEN", version: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }));
    await createConversation();
    expect(fetchMock).toHaveBeenLastCalledWith("/v1/customer/chat/conversations", expect.objectContaining({ method: "POST", credentials: "include", headers: expect.objectContaining({ "X-CSRF-Token": "chat-token" }) }));
  });

  it("sends a client-generated request id for retry-safe turns", async () => {
    document.cookie = "techdemo_csrf=chat-token; Path=/";
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(jsonResponse({}));
    await sendChatMessage("conversation/1", "Where is my order?", "request-12345");
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ message: "Where is my order?", client_request_id: "request-12345" });
  });
});
