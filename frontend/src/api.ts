/** Thin fetch wrapper: JSON in/out, cookies, and the CSRF header the server requires. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      "X-Requested-With": "LanGamesHub",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const data: unknown = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data) ?? `Request failed (${response.status})`);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function errorMessage(data: unknown): string | null {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Invalid input";
  }
  return null;
}

export function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
