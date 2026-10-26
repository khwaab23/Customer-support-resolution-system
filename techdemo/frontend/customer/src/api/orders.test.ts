import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerOrder, getCustomerOrders } from "./orders";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("orders API", () => {
  afterEach(() => {
    fetchMock.mockReset();
  });

  it("loads recent orders through the relative customer endpoint", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ orders: [] }));

    await expect(getCustomerOrders()).resolves.toEqual({ orders: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/customer/orders?limit=10",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("encodes an order identifier for the customer-owned details endpoint", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        order_id: "ORDER/1",
        ordered_at: "2026-01-02",
        status: "PAID",
        currency: "USD",
        total_minor: 1299,
      }),
    );

    await getCustomerOrder("ORDER/1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/customer/orders/ORDER%2F1",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
