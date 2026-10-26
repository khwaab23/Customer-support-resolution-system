import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerOrder } from "../api/orders";
import { createTicket } from "../api/tickets";
import { OrderDetailsPage } from "./OrderDetailsPage";

vi.mock("../api/orders", () => ({
  getCustomerOrder: vi.fn(),
}));
vi.mock("../api/tickets", () => ({
  createTicket: vi.fn(),
}));

const getCustomerOrderMock = vi.mocked(getCustomerOrder);
const createTicketMock = vi.mocked(createTicket);

function renderSupportForm() {
  return render(
    <MemoryRouter initialEntries={["/orders/ORDER-001"]}>
      <Routes>
        <Route path="/orders/:orderId" element={<OrderDetailsPage />} />
        <Route path="/tickets/:ticketId" element={<p>Created ticket page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function setLoadedOrder() {
  getCustomerOrderMock.mockResolvedValue({
    order_id: "ORDER-001",
    ordered_at: "2026-01-02",
    status: "COMPLETED",
    currency: "USD",
    total_minor: 2500,
  });
}

describe("order support form", () => {
  afterEach(() => {
    getCustomerOrderMock.mockReset();
    createTicketMock.mockReset();
  });

  it("validates an empty support message", async () => {
    setLoadedOrder();
    const user = userEvent.setup();
    renderSupportForm();

    await user.click(await screen.findByRole("button", { name: "Get support" }));
    await user.click(screen.getByRole("button", { name: "Submit support request" }));

    expect(
      screen.getByText("Describe the issue before submitting your support request."),
    ).toBeInTheDocument();
    expect(createTicketMock).not.toHaveBeenCalled();
  });

  it("submits a ticket once and navigates to its details page", async () => {
    setLoadedOrder();
    createTicketMock.mockResolvedValue({
      ticket_id: "TKT-NEW",
      order_id: "ORDER-001",
      message: "Please help with my order.",
      status: "OPEN",
      created_at: "2026-01-02T12:00:00Z",
    });
    const user = userEvent.setup();
    renderSupportForm();

    await user.click(await screen.findByRole("button", { name: "Get support" }));
    await user.type(screen.getByLabelText("How can we help?"), "Please help with my order.");
    await user.click(screen.getByRole("button", { name: "Submit support request" }));

    expect(createTicketMock).toHaveBeenCalledWith("ORDER-001", "Please help with my order.");
    expect(await screen.findByText("Created ticket page")).toBeInTheDocument();
  });

  it("does not submit duplicate requests while one submission is pending", async () => {
    setLoadedOrder();
    let resolveTicket: (value: Awaited<ReturnType<typeof createTicket>>) => void;
    createTicketMock.mockReturnValue(
      new Promise((resolve) => {
        resolveTicket = resolve;
      }),
    );
    const user = userEvent.setup();
    renderSupportForm();

    await user.click(await screen.findByRole("button", { name: "Get support" }));
    await user.type(screen.getByLabelText("How can we help?"), "Please help.");
    const submitButton = screen.getByRole("button", { name: "Submit support request" });
    await user.click(submitButton);
    await user.click(submitButton);

    expect(createTicketMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();

    resolveTicket!({
      ticket_id: "TKT-NEW",
      order_id: "ORDER-001",
      message: "Please help.",
      status: "OPEN",
      created_at: "2026-01-02T12:00:00Z",
    });
  });
});
