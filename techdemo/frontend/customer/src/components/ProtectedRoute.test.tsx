import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../contexts/AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";

function renderRoute(value: AuthContextValue) {
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<p>Customer home</p>} />
          </Route>
          <Route path="/login" element={<p>Login page</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const noOp = vi.fn();

describe("ProtectedRoute", () => {
  it("renders a loading state while session restoration is in progress", () => {
    renderRoute({
      user: null,
      isLoading: true,
      error: null,
      login: noOp,
      logout: noOp,
      clearError: noOp,
    });

    expect(screen.getByText("Restoring your secure session…")).toBeInTheDocument();
  });

  it("redirects an unauthenticated visitor to login", () => {
    renderRoute({
      user: null,
      isLoading: false,
      error: null,
      login: noOp,
      logout: noOp,
      clearError: noOp,
    });

    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("renders the protected customer route for a customer session", () => {
    renderRoute({
      user: { user_id: "user-1", role: "CUSTOMER", customer_id: "C-1" },
      isLoading: false,
      error: null,
      login: noOp,
      logout: noOp,
      clearError: noOp,
    });

    expect(screen.getByText("Customer home")).toBeInTheDocument();
  });
});
