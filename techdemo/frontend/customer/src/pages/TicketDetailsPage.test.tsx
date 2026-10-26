import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { getCustomerTicket } from "../api/tickets";
import { TicketDetailsPage } from "./TicketDetailsPage";

vi.mock("../api/tickets", () => ({
  getCustomerTicket: vi.fn(),
}));

const getCustomerTicketMock = vi.mocked(getCustomerTicket);

function renderDetails(state?: object) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/tickets/TKT-001", state }]}>
      <Routes>
        <Route path="/tickets/:ticketId" element={<TicketDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TicketDetailsPage", () => {
  afterEach(() => {
    getCustomerTicketMock.mockReset();
  });

  it("displays the ticket fields returned by the backend", async () => {
    getCustomerTicketMock.mockResolvedValue({
      ticket_id: "TKT-001",
      order_id: "ORDER-001",
      message: "Please help with my order.",
      status: "OPEN",
      created_at: "2026-01-02T12:00:00Z",
    });
    renderDetails({ createdTicket: { ticketId: "TKT-001", status: "OPEN" } });

    expect(await screen.findByText("Please help with my order.")).toBeInTheDocument();
    expect(screen.getByText("Ticket TKT-001 was submitted with status Open.")).toBeInTheDocument();
    expect(screen.getByText("ORDER-001")).toBeInTheDocument();
  });

  it("shows a not-found message for a 404", async () => {
    getCustomerTicketMock.mockRejectedValue(new ApiError("Ticket not found", 404));
    renderDetails();

    expect(
      await screen.findByText("We could not find this support ticket. It may not belong to your account."),
    ).toBeInTheDocument();
  });
});
