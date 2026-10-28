import { afterEach, describe, expect, it, vi } from "vitest";

import { decide, login } from "./api";

const fetchMock = vi.fn();

Object.defineProperty(globalThis, "fetch", { value: fetchMock, writable: true });
Object.defineProperty(globalThis, "document", {
  value: { cookie: "techdemo_csrf=safe-token" },
  writable: true,
});

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => fetchMock.mockReset());

describe("admin API client", () => {
  it("initializes CSRF and includes the token for login", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    fetchMock.mockResolvedValueOnce(response({ user_id: "u", role: "ADMIN", customer_id: null }));

    await login("admin@example.test", "not-logged");

    expect(fetchMock).toHaveBeenLastCalledWith("/v1/auth/login", expect.objectContaining({
      credentials: "include", method: "POST", headers: expect.objectContaining({ "X-CSRF-Token": "safe-token" }),
    }));
  });

  it("sends only the decision, reason, and optimistic version", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    fetchMock.mockResolvedValueOnce(response({ review_id: "r" }));

    await decide("r", "REQUEST_MORE_INFORMATION", "Need a receipt", 4);

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ decision: "REQUEST_MORE_INFORMATION", reason: "Need a receipt", version: 4 });
  });
});
