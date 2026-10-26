import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { getCurrentUser, login, logout } from "./auth";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authentication API", () => {
  afterEach(() => {
    fetchMock.mockReset();
    document.cookie = "techdemo_csrf=; Max-Age=0; Path=/";
  });

  it("initializes CSRF and sends the token when logging in", async () => {
    document.cookie = "techdemo_csrf=csrf-token; Path=/";
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "user-1", role: "CUSTOMER", customer_id: "C-1" }),
      );

    await expect(
      login({ email: "customer@example.test", password: "not-a-real-password" }),
    ).resolves.toMatchObject({ role: "CUSTOMER", customer_id: "C-1" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/auth/csrf",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/auth/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token" }),
      }),
    );
  });

  it("sends a current CSRF token when logging out", async () => {
    document.cookie = "techdemo_csrf=fresh-token; Path=/";
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }));

    await expect(logout()).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/v1/auth/logout",
      expect.objectContaining({
        method: "POST",
        headers: { "X-CSRF-Token": "fresh-token" },
      }),
    );
  });

  it("surfaces a backend authentication failure without treating it as a user", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Not authenticated" }, 401));

    await expect(getCurrentUser()).rejects.toBeInstanceOf(ApiError);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Not authenticated" }, 401));
    await getCurrentUser().catch((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      if (error instanceof ApiError) {
        expect(error.status).toBe(401);
        expect(error.message).toBe("Not authenticated");
      }
    });
  });
});
