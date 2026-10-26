import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../contexts/AuthContext";
import { LoginPage } from "./LoginPage";

function renderLogin(overrides: Partial<AuthContextValue> = {}) {
  const value: AuthContextValue = {
    user: null,
    isLoading: false,
    error: null,
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn().mockResolvedValue(undefined),
    clearError: vi.fn(),
    ...overrides,
  };

  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
  return value;
}

describe("LoginPage", () => {
  it("shows local validation errors before submitting an empty form", async () => {
    const user = userEvent.setup();
    const value = renderLogin();

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(value.login).not.toHaveBeenCalled();
  });

  it("submits valid customer credentials through the authentication context", async () => {
    const user = userEvent.setup();
    const value = renderLogin();

    await user.type(screen.getByLabelText("Email address"), "customer@example.test");
    await user.type(screen.getByLabelText("Password"), "not-a-real-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(value.login).toHaveBeenCalledWith({
      email: "customer@example.test",
      password: "not-a-real-password",
    });
  });
});
