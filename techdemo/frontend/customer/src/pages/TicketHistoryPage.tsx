import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { getCustomerTickets, type CustomerTicket } from "../api/tickets";
import { formatTicketCreatedAt, formatTicketStatus } from "../utils/ticketFormatting";

function ticketListErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (error instanceof TypeError) {
    return "We could not reach TechDemo. Please try again shortly.";
  }
  return "We could not load your support tickets. Please try again shortly.";
}

export function TicketHistoryPage() {
  const [tickets, setTickets] = useState<CustomerTicket[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadTickets() {
      setIsLoading(true);
      setError(null);
      try {
        const response = await getCustomerTickets();
        if (isCurrent) {
          setTickets(response.tickets);
        }
      } catch (caughtError) {
        if (isCurrent) {
          setError(ticketListErrorMessage(caughtError));
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadTickets();
    return () => {
      isCurrent = false;
    };
  }, []);

  return (
    <main className="home-page">
      <section className="home-shell" aria-labelledby="ticket-history-heading">
        <header className="portal-header">
          <div className="brand-lockup" aria-label="TechDemo">
            <span className="brand-mark" aria-hidden="true">T</span>
            <span>TechDemo</span>
          </div>
          <Link className="text-link" to="/">← Back to orders</Link>
        </header>

        <div className="welcome-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Support</p>
              <h1 id="ticket-history-heading">My support tickets</h1>
            </div>
            <p className="section-caption">Your 10 most recent requests</p>
          </div>

          {isLoading && (
            <div className="orders-loading" aria-live="polite">
              <span className="loading-spinner" aria-hidden="true" />
              <p>Loading your support tickets…</p>
            </div>
          )}

          {error && !isLoading && <div className="orders-message orders-message-error" role="alert">{error}</div>}

          {!isLoading && !error && tickets.length === 0 && (
            <div className="orders-message">
              <h2>No support tickets yet</h2>
              <p>Open an order and select Get support if you need help.</p>
            </div>
          )}

          {!isLoading && !error && tickets.length > 0 && (
            <ol className="tickets-list">
              {tickets.map((ticket) => (
                <li key={ticket.ticket_id}>
                  <Link className="ticket-row" to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>
                    <span className="ticket-id">{ticket.ticket_id}</span>
                    <span className="ticket-message">{ticket.message}</span>
                    <span className="ticket-created">{formatTicketCreatedAt(ticket.created_at)}</span>
                    <span className="order-status">{formatTicketStatus(ticket.status)}</span>
                    <span className="order-chevron" aria-hidden="true">›</span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </main>
  );
}
