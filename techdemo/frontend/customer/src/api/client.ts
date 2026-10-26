export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiErrorBody = {
  detail?: unknown;
};

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === "object" && value !== null;
}

async function responseMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (isApiErrorBody(body) && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Error responses are not required to be JSON.
  }

  return "The request could not be completed.";
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/v1/")) {
    throw new Error("API requests must use a relative /v1/ path.");
  }

  const response = await fetch(path, {
    ...options,
    credentials: "include",
  });

  if (!response.ok) {
    throw new ApiError(await responseMessage(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
