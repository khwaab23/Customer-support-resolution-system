import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { getCustomerTicket, type CustomerTicket } from "../api/tickets";
import { formatTicketCreatedAt, formatTicketStatus } from "../utils/ticketFormatting";

type CreatedTicketState = {
  createdTicket?: {
    ticketId: string;
    status: string;
  };
};

function ticketDetailsErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "We could not find this support ticket. It may not belong to your account.";
  }
  if (error instanceof ApiError && error.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (error instanceof TypeError) {
    return "We could not reach TechDemo. Please try again shortly.";
  }
  return "We could not load this support ticket. Please try again shortly.";
}

export function TicketDetailsPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const location = useLocation();
  const createdTicket = (location.state as CreatedTicketState | null)?.createdTicket;
  const [ticket, setTicket] = useState<CustomerTicket | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadTicket() {
      if (!ticketId) {
        if (isCurrent) {
          setError("We could not identify the requested support ticket.");
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const response = await getCustomerTicket(ticketId);
        if (isCurrent) {
          setTicket(response);
        }
      } catch (caughtError) {
        if (isCurrent) {
          setError(ticketDetailsErrorMessage(caughtError));
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadTicket();
    return () => {
      isCurrent = false;
    };
  }, [ticketId]);

  return (
    <main className="home-page">
      <section className="home-shell" aria-labelledby="ticket-details-heading">
        <header className="portal-header">
          <div className="brand-lockup" aria-label="TechDemo">
            <span className="brand-mark" aria-hidden="true">T</span>
            <span>TechDemo</span>
          </div>
          <Link className="text-link" to="/tickets">← Back to tickets</Link>
        </header>

        <div className="welcome-card">
          <p className="eyebrow">Support ticket</p>
          <h1 id="ticket-details-heading">Ticket details</h1>

          {createdTicket && createdTicket.ticketId === ticketId && (
            <div className="ticket-success" role="status">
              Ticket {createdTicket.ticketId} was submitted with status {formatTicketStatus(createdTicket.status)}.
            </div>
          )}

          {isLoading && (
            <div className="orders-loading" aria-live="polite">
              <span className="loading-spinner" aria-hidden="true" />
              <p>Loading support ticket…</p>
            </div>
          )}

          {error && !isLoading && <div className="form-alert" role="alert">{error}</div>}

          {ticket && !isLoading && !error && (
            <dl className="ticket-details-list">
              <div>
                <dt>Ticket ID</dt>
                <dd>{ticket.ticket_id}</dd>
              </div>
              <div>
                <dt>Associated order</dt>
                <dd>{ticket.order_id ?? "Not linked to an order"}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd><span className="order-status">{formatTicketStatus(ticket.status)}</span></dd>
              </div>
              <div>
                <dt>Submitted</dt>
                <dd>{formatTicketCreatedAt(ticket.created_at)}</dd>
              </div>
              <div className="ticket-message-detail">
                <dt>Your message</dt>
                <dd>{ticket.message}</dd>
              </div>
            </dl>
          )}
        </div>
      </section>
    </main>
  );
}
