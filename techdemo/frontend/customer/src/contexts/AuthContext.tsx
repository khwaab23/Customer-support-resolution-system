import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { ApiError } from "../api/client";
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  type AuthenticatedUser,
  type LoginCredentials,
} from "../api/auth";

export type AuthContextValue = {
  user: AuthenticatedUser | null;
  isLoading: boolean;
  error: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
};

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function userFacingError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Your email or password was not recognized.";
  }

  if (error instanceof TypeError) {
    return "We could not reach TechDemo. Please try again shortly.";
  }

  return fallback;
}

function assertCustomer(user: AuthenticatedUser): void {
  if (user.role !== "CUSTOMER" || !user.customer_id) {
    throw new Error("This customer portal is only available to customer accounts.");
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const restoreSession = useCallback(async () => {
    setIsLoading(true);
    try {
      const restoredUser = await getCurrentUser();
      assertCustomer(restoredUser);
      setUser(restoredUser);
      setError(null);
    } catch (caughtError) {
      setUser(null);
      if (!(caughtError instanceof ApiError && caughtError.status === 401)) {
        setError(userFacingError(caughtError, "Your session could not be restored."));
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setError(null);
    try {
      const authenticatedUser = await loginRequest(credentials);
      assertCustomer(authenticatedUser);
      setUser(authenticatedUser);
    } catch (caughtError) {
      const message = userFacingError(caughtError, "We could not sign you in.");
      setUser(null);
      setError(message);
      throw new Error(message, { cause: caughtError });
    }
  }, []);

  const logout = useCallback(async () => {
    setError(null);
    try {
      await logoutRequest();
      setUser(null);
    } catch (caughtError) {
      const message = userFacingError(caughtError, "We could not sign you out.");
      setError(message);
      throw new Error(message, { cause: caughtError });
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      error,
      login,
      logout,
      clearError: () => setError(null),
    }),
    [error, isLoading, login, logout, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
