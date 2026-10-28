import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getCustomerOrders, type CustomerOrder } from "../api/orders";
import { ApiError } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import {
  formatOrderDate,
  formatOrderStatus,
  formatOrderTotal,
} from "../utils/orderFormatting";

function orderErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (error instanceof TypeError) {
    return "We could not reach TechDemo. Please try again shortly.";
  }
  return "We could not load your recent orders. Please try again shortly.";
}

export function HomePage() {
  const { user, logout, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [isLoadingOrders, setIsLoadingOrders] = useState(true);
  const [ordersError, setOrdersError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadOrders() {
      setIsLoadingOrders(true);
      setOrdersError(null);
      try {
        const response = await getCustomerOrders();
        if (isCurrent) {
          setOrders(response.orders);
        }
      } catch (caughtError) {
        if (isCurrent) {
          setOrdersError(orderErrorMessage(caughtError));
        }
      } finally {
        if (isCurrent) {
          setIsLoadingOrders(false);
        }
      }
    }

    void loadOrders();
    return () => {
      isCurrent = false;
    };
  }, []);

  if (!user) {
    return null;
  }

  async function handleLogout() {
    setIsLoggingOut(true);
    clearError();
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch {
      // Keep the customer on the page; the context exposes the safe error message.
    } finally {
      setIsLoggingOut(false);
    }
  }

  return (
    <main className="home-page">
      <section className="home-shell" aria-labelledby="welcome-heading">
        <header className="portal-header">
          <div className="brand-lockup" aria-label="TechDemo">
            <span className="brand-mark" aria-hidden="true">T</span>
            <span>TechDemo</span>
          </div>
          <div className="portal-actions">
            <Link className="text-link" to="/tickets">My support tickets</Link>
            <Link className="text-link" to="/support">AI Support Chat</Link>
            <button
              type="button"
              className="text-button"
              onClick={() => void handleLogout()}
              disabled={isLoggingOut}
            >
              {isLoggingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>

        <div className="welcome-card">
          <div className="identity-row">
            <div>
              <p className="eyebrow">Your account</p>
              <h1 id="welcome-heading">Welcome back</h1>
              <p className="customer-identifier">Account ID: {user.user_id}</p>
            </div>
            <span className="role-badge">{user.role}</span>
          </div>

          {error && <div className="form-alert" role="alert">{error}</div>}

          <section className="orders-section" aria-labelledby="recent-orders-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Order history</p>
                <h2 id="recent-orders-heading">Recent orders</h2>
              </div>
              <p className="section-caption">Your 10 most recent orders</p>
            </div>

            {isLoadingOrders && (
              <div className="orders-loading" aria-live="polite">
                <span className="loading-spinner" aria-hidden="true" />
                <p>Loading your recent orders…</p>
              </div>
            )}

            {ordersError && !isLoadingOrders && (
              <div className="orders-message orders-message-error" role="alert">
                {ordersError}
              </div>
            )}

            {!isLoadingOrders && !ordersError && orders.length === 0 && (
              <div className="orders-message">
                <h3>No orders yet</h3>
                <p>When you place an order with TechDemo, it will appear here.</p>
              </div>
            )}

            {!isLoadingOrders && !ordersError && orders.length > 0 && (
              <ol className="orders-list">
                {orders.map((order) => (
                  <li key={order.order_id}>
                    <Link
                      className="order-row"
                      to={`/orders/${encodeURIComponent(order.order_id)}`}
                    >
                      <span className="order-id">{order.order_id}</span>
                      <span className="order-date">{formatOrderDate(order.ordered_at)}</span>
                      <span className="order-status">{formatOrderStatus(order.status)}</span>
                      <span className="order-total">
                        {formatOrderTotal(order.total_minor, order.currency)}
                      </span>
                      <span className="order-chevron" aria-hidden="true">›</span>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <dl className="identity-details">
            <div>
              <dt>Customer ID</dt>
              <dd>{user.customer_id}</dd>
            </div>
          </dl>
        </div>
      </section>
    </main>
  );
}
