import { afterEach, describe, expect, it, vi } from "vitest";

import { getCsrfHeaders } from "./auth";
import { createTicket, getCustomerTicket, getCustomerTickets } from "./tickets";

vi.mock("./auth", () => ({
  getCsrfHeaders: vi.fn(),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const getCsrfHeadersMock = vi.mocked(getCsrfHeaders);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const ticket = {
  ticket_id: "TKT-001",
  order_id: "ORDER-001",
  message: "Please help with my order.",
  status: "OPEN",
  created_at: "2026-01-02T12:00:00Z",
};

describe("tickets API", () => {
  afterEach(() => {
    fetchMock.mockReset();
    getCsrfHeadersMock.mockReset();
  });

  it("creates a ticket with the existing CSRF and cookie safeguards", async () => {
    getCsrfHeadersMock.mockResolvedValue({ "X-CSRF-Token": "csrf-token" });
    fetchMock.mockResolvedValueOnce(jsonResponse(ticket));

    await expect(
      createTicket("ORDER-001", "Please help with my order."),
    ).resolves.toEqual(ticket);

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/customer/tickets",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token",
        },
        body: JSON.stringify({
          order_id: "ORDER-001",
          message: "Please help with my order.",
        }),
      }),
    );
  });

  it("loads ticket lists and an encoded individual ticket path", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ tickets: [ticket] }))
      .mockResolvedValueOnce(jsonResponse(ticket));

    await expect(getCustomerTickets()).resolves.toEqual({ tickets: [ticket] });
    await expect(getCustomerTicket("TKT/001")).resolves.toEqual(ticket);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/v1/customer/tickets?limit=10",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/v1/customer/tickets/TKT%2F001",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
