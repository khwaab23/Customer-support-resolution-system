import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerOrders } from "../api/orders";
import { AuthContext, type AuthContextValue } from "../contexts/AuthContext";
import { HomePage } from "./HomePage";

vi.mock("../api/orders", () => ({
  getCustomerOrders: vi.fn(),
}));

const getCustomerOrdersMock = vi.mocked(getCustomerOrders);

function renderHome() {
  const auth: AuthContextValue = {
    user: { user_id: "user-1", role: "CUSTOMER", customer_id: "CUST-001" },
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("HomePage order history", () => {
  afterEach(() => {
    getCustomerOrdersMock.mockReset();
  });

  it("shows a loading state while recent orders are being fetched", () => {
    getCustomerOrdersMock.mockReturnValue(new Promise(() => undefined));
    renderHome();

    expect(screen.getByText("Loading your recent orders…")).toBeInTheDocument();
  });

  it("renders orders in the sequence returned by the backend", async () => {
    getCustomerOrdersMock.mockResolvedValue({
      orders: [
        {
          order_id: "ORDER-NEWEST",
          ordered_at: "2026-03-02",
          status: "PAID",
          currency: "USD",
          total_minor: 1299,
        },
        {
          order_id: "ORDER-OLDER",
          ordered_at: "2026-03-01",
          status: "PROCESSING",
          currency: "USD",
          total_minor: 4500,
        },
      ],
    });
    renderHome();

    const newestOrder = await screen.findByRole("link", { name: /ORDER-NEWEST/i });
    const olderOrder = screen.getByRole("link", { name: /ORDER-OLDER/i });

    expect(newestOrder.compareDocumentPosition(olderOrder)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.getByText("$12.99")).toBeInTheDocument();
    expect(screen.getByText("Paid")).toBeInTheDocument();
  });

  it("shows a friendly empty state", async () => {
    getCustomerOrdersMock.mockResolvedValue({ orders: [] });
    renderHome();

    expect(await screen.findByText("No orders yet")).toBeInTheDocument();
  });

  it("shows a safe error when the request fails", async () => {
    getCustomerOrdersMock.mockRejectedValue(new TypeError("network failure"));
    renderHome();

    expect(
      await screen.findByText("We could not reach TechDemo. Please try again shortly."),
    ).toBeInTheDocument();
  });
});
