import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCustomerTickets } from "../api/tickets";
import { TicketHistoryPage } from "./TicketHistoryPage";

vi.mock("../api/tickets", () => ({
  getCustomerTickets: vi.fn(),
}));

const getCustomerTicketsMock = vi.mocked(getCustomerTickets);

function renderHistory() {
  return render(
    <MemoryRouter>
      <TicketHistoryPage />
    </MemoryRouter>,
  );
}

describe("TicketHistoryPage", () => {
  afterEach(() => {
    getCustomerTicketsMock.mockReset();
  });

  it("shows a loading state while tickets are fetched", () => {
    getCustomerTicketsMock.mockReturnValue(new Promise(() => undefined));
    renderHistory();

    expect(screen.getByText("Loading your support tickets…")).toBeInTheDocument();
  });

  it("renders ticket rows in the backend response order", async () => {
    getCustomerTicketsMock.mockResolvedValue({
      tickets: [
        {
          ticket_id: "TKT-NEWEST",
          order_id: "ORDER-001",
          message: "Newest request",
          status: "OPEN",
          created_at: "2026-01-02T12:00:00Z",
        },
        {
          ticket_id: "TKT-OLDER",
          order_id: "ORDER-002",
          message: "Older request",
          status: "OPEN",
          created_at: "2026-01-01T12:00:00Z",
        },
      ],
    });
    renderHistory();

    const newest = await screen.findByRole("link", { name: /TKT-NEWEST/i });
    const older = screen.getByRole("link", { name: /TKT-OLDER/i });

    expect(newest.compareDocumentPosition(older)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.getByText("Newest request")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    getCustomerTicketsMock.mockResolvedValue({ tickets: [] });
    renderHistory();

    expect(await screen.findByText("No support tickets yet")).toBeInTheDocument();
  });

  it("shows a safe network error", async () => {
    getCustomerTicketsMock.mockRejectedValue(new TypeError("network failure"));
    renderHistory();

    expect(
      await screen.findByText("We could not reach TechDemo. Please try again shortly."),
    ).toBeInTheDocument();
  });
});
