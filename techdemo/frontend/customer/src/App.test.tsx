import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthContext, type AuthContextValue } from "./contexts/AuthContext";

describe("customer routes", () => {
  it("redirects an unauthenticated visitor away from ticket history", () => {
    const value: AuthContextValue = {
      user: null,
      isLoading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    };

    render(
      <AuthContext.Provider value={value}>
        <MemoryRouter initialEntries={["/tickets"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });
});
