import { apiRequest } from "./client";

const CSRF_COOKIE_NAME = "techdemo_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";

export type UserRole = "CUSTOMER" | "ADMIN";

export type AuthenticatedUser = {
  user_id: string;
  role: UserRole;
  customer_id: string | null;
};

export type LoginCredentials = {
  email: string;
  password: string;
};

function readCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));

  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : undefined;
}

export async function getCsrfHeaders(): Promise<Record<string, string>> {
  await initializeCsrf();
  const csrfToken = readCookie(CSRF_COOKIE_NAME);

  if (!csrfToken) {
    throw new Error("The CSRF token could not be initialized.");
  }

  return { [CSRF_HEADER_NAME]: csrfToken };
}

export async function initializeCsrf(): Promise<void> {
  await apiRequest<void>("/v1/auth/csrf");
}

export async function login(
  credentials: LoginCredentials,
): Promise<AuthenticatedUser> {
  const csrfHeader = await getCsrfHeaders();

  return apiRequest<AuthenticatedUser>("/v1/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeader,
    },
    body: JSON.stringify(credentials),
  });
}

export function getCurrentUser(): Promise<AuthenticatedUser> {
  return apiRequest<AuthenticatedUser>("/v1/auth/me");
}

export async function logout(): Promise<void> {
  const csrfHeader = await getCsrfHeaders();
  await apiRequest<void>("/v1/auth/logout", {
    method: "POST",
    headers: csrfHeader,
  });
}
