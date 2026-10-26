import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerOrder } from "../api/orders";
import { ApiError } from "../api/client";
import { OrderDetailsPage } from "./OrderDetailsPage";

vi.mock("../api/orders", () => ({
  getCustomerOrder: vi.fn(),
}));

const getCustomerOrderMock = vi.mocked(getCustomerOrder);

function renderDetails(path = "/orders/ORDER-001") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/orders/:orderId" element={<OrderDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OrderDetailsPage", () => {
  afterEach(() => {
    getCustomerOrderMock.mockReset();
  });

  it("loads and displays only fields supplied by the order API", async () => {
    getCustomerOrderMock.mockResolvedValue({
      order_id: "ORDER-001",
      ordered_at: "2026-03-03",
      status: "PROCESSING",
      currency: "USD",
      total_minor: 2500,
    });
    renderDetails();

    expect(await screen.findByText("ORDER-001")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Back to orders" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("shows a customer-safe not-found message for a 404", async () => {
    getCustomerOrderMock.mockRejectedValue(new ApiError("Order not found", 404));
    renderDetails("/orders/NOT-OWNED");

    expect(
      await screen.findByText("We could not find this order. It may not belong to your account."),
    ).toBeInTheDocument();
  });
});
