import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../contexts/AuthContext";

export function ProtectedRoute() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <main className="loading-page" aria-live="polite">
        <div className="loading-card">
          <span className="loading-spinner" aria-hidden="true" />
          <p>Restoring your secure session…</p>
        </div>
      </main>
    );
  }

  if (!user || user.role !== "CUSTOMER" || !user.customer_id) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
