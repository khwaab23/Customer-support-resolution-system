import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { getCustomerOrder, type CustomerOrder } from "../api/orders";
import { ApiError } from "../api/client";
import { createTicket } from "../api/tickets";
import {
  formatOrderDate,
  formatOrderStatus,
  formatOrderTotal,
} from "../utils/orderFormatting";

function detailsErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "We could not find this order. It may not belong to your account.";
  }
  if (error instanceof ApiError && error.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (error instanceof TypeError) {
    return "We could not reach TechDemo. Please try again shortly.";
  }
  return "We could not load this order. Please try again shortly.";
}

export function OrderDetailsPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [order, setOrder] = useState<CustomerOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSupportFormOpen, setIsSupportFormOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submissionInFlight = useRef(false);

  useEffect(() => {
    let isCurrent = true;

    async function loadOrder() {
      if (!orderId) {
        if (isCurrent) {
          setError("We could not identify the requested order.");
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const response = await getCustomerOrder(orderId);
        if (isCurrent) {
          setOrder(response);
        }
      } catch (caughtError) {
        if (isCurrent) {
          setError(detailsErrorMessage(caughtError));
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadOrder();
    return () => {
      isCurrent = false;
    };
  }, [orderId]);

  function openSupportForm() {
    setFormError(null);
    setIsSupportFormOpen(true);
  }

  async function submitSupportRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedMessage = message.trim();

    if (!trimmedMessage) {
      setFormError("Describe the issue before submitting your support request.");
      return;
    }
    if (!order || submissionInFlight.current) {
      return;
    }

    submissionInFlight.current = true;
    setIsSubmitting(true);
    setFormError(null);
    try {
      const ticket = await createTicket(order.order_id, trimmedMessage);
      navigate(`/tickets/${encodeURIComponent(ticket.ticket_id)}`, {
        replace: true,
        state: {
          createdTicket: {
            ticketId: ticket.ticket_id,
            status: ticket.status,
          },
        },
      });
    } catch (caughtError) {
      if (caughtError instanceof ApiError && caughtError.status === 404) {
        setFormError("This order is no longer available for support.");
      } else if (caughtError instanceof TypeError) {
        setFormError("We could not reach TechDemo. Please try again shortly.");
      } else {
        setFormError("We could not submit your support request. Please try again.");
      }
    } finally {
      submissionInFlight.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <main className="home-page">
      <section className="home-shell" aria-labelledby="order-details-heading">
        <header className="portal-header">
          <div className="brand-lockup" aria-label="TechDemo">
            <span className="brand-mark" aria-hidden="true">T</span>
            <span>TechDemo</span>
          </div>
          <Link className="text-link" to="/">← Back to orders</Link>
        </header>

        <div className="welcome-card">
          <p className="eyebrow">Order details</p>
          <h1 id="order-details-heading">Order details</h1>

          {isLoading && (
            <div className="orders-loading" aria-live="polite">
              <span className="loading-spinner" aria-hidden="true" />
              <p>Loading order details…</p>
            </div>
          )}

          {error && !isLoading && <div className="form-alert" role="alert">{error}</div>}

          {order && !isLoading && !error && (
            <>
              <dl className="order-details-list">
                <div>
                  <dt>Order ID</dt>
                  <dd>{order.order_id}</dd>
                </div>
                <div>
                  <dt>Order date</dt>
                  <dd>{formatOrderDate(order.ordered_at)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd><span className="order-status">{formatOrderStatus(order.status)}</span></dd>
                </div>
                <div>
                  <dt>Total</dt>
                  <dd>{formatOrderTotal(order.total_minor, order.currency)}</dd>
                </div>
              </dl>

              {!isSupportFormOpen && (
                <section className="support-action" aria-labelledby="support-heading">
                  <div>
                    <h2 id="support-heading">Need help with this order?</h2>
                    <p>Send a support request and our team will review it.</p>
                  </div>
                  <button type="button" className="primary-button compact-button" onClick={openSupportForm}>
                    Get support
                  </button>
                </section>
              )}

              {isSupportFormOpen && (
                <section className="support-form-section" aria-labelledby="support-form-heading">
                  <h2 id="support-form-heading">Tell us what happened</h2>
                  <p>We will attach this request to the selected order.</p>

                  <form className="support-form" onSubmit={submitSupportRequest} noValidate>
                    <label htmlFor="support-order-id">Selected order</label>
                    <input id="support-order-id" value={order.order_id} readOnly />

                    <label htmlFor="support-message">How can we help?</label>
                    <textarea
                      id="support-message"
                      value={message}
                      onChange={(event) => {
                        setMessage(event.target.value);
                        setFormError(null);
                      }}
                      maxLength={5000}
                      rows={5}
                      aria-invalid={Boolean(formError)}
                      aria-describedby={formError ? "support-form-error" : undefined}
                    />
                    {formError && <p className="field-error" id="support-form-error">{formError}</p>}

                    <div className="support-form-actions">
                      <button type="submit" className="primary-button" disabled={isSubmitting}>
                        {isSubmitting ? "Submitting…" : "Submit support request"}
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        disabled={isSubmitting}
                        onClick={() => setIsSupportFormOpen(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </section>
              )}
            </>
          )}
        </div>
      </section>
    </main>
  );
}
