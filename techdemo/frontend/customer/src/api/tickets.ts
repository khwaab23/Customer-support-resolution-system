import { getCsrfHeaders } from "./auth";
import { apiRequest } from "./client";

export type CustomerTicket = {
  ticket_id: string;
  order_id: string | null;
  message: string;
  status: string;
  created_at: string;
  // Intentionally sanitized: no reviewer identity, notes, or workflow ID.
  review_status?: string;
};

type CustomerTicketListResponse = {
  tickets: CustomerTicket[];
};

function validLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("Ticket limit must be an integer between 1 and 50.");
  }
  return limit;
}

export async function createTicket(
  orderId: string,
  message: string,
): Promise<CustomerTicket> {
  const csrfHeaders = await getCsrfHeaders();
  return apiRequest<CustomerTicket>("/v1/customer/tickets", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders,
    },
    body: JSON.stringify({ order_id: orderId, message }),
  });
}

export function getCustomerTickets(
  limit = 10,
): Promise<CustomerTicketListResponse> {
  const query = new URLSearchParams({ limit: String(validLimit(limit)) });
  return apiRequest<CustomerTicketListResponse>(`/v1/customer/tickets?${query}`);
}

export function getCustomerTicket(ticketId: string): Promise<CustomerTicket> {
  return apiRequest<CustomerTicket>(
    `/v1/customer/tickets/${encodeURIComponent(ticketId)}`,
  );
}
