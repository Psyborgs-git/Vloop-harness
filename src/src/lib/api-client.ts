export class ApiError extends Error {
  readonly status: number | null;
  readonly body: unknown;

  constructor(
    message: string,
    status: number | null = null,
    body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? (value as Record<string, unknown>) : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readString(
  record: Record<string, unknown>,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = record[key];
    if (value === null || value === undefined) {
      continue;
    }
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return null;
}

export function readNumber(
  record: Record<string, unknown>,
  ...keys: string[]
): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

export function readBoolean(
  record: Record<string, unknown>,
  ...keys: string[]
): boolean | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (["true", "1", "yes", "on"].includes(normalized)) {
        return true;
      }
      if (["false", "0", "no", "off"].includes(normalized)) {
        return false;
      }
    }
  }
  return null;
}

export function parseBody(text: string, contentType: string | null): unknown {
  if (!text) {
    return null;
  }

  if (contentType?.includes("application/json")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  const record = asRecord(payload);
  return (
    readString(
      record,
      "message",
      "error",
      "detail",
      "lastError",
      "last_error",
    ) ??
    (fallback || "Request failed")
  );
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

interface RequestCandidate {
  path: string;
  method?: string;
  body?: unknown;
}

const FALLBACK_STATUSES = new Set([404, 405]);

export async function requestJson<T>(
  path: string,
  methodOrInit?: string | RequestInit,
  body?: unknown,
): Promise<T> {
  const init: RequestInit =
    typeof methodOrInit === "string"
      ? {
          method: methodOrInit,
          body: body !== undefined ? JSON.stringify(body) : undefined,
        }
      : (methodOrInit ?? {});
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    headers,
  });

  const text = await response.text();
  const payload = parseBody(text, response.headers.get("Content-Type"));

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(payload, response.statusText),
      response.status,
      payload,
    );
  }

  return payload as T;
}

export async function requestWithFallback<T>(
  candidates: RequestCandidate[],
): Promise<T> {
  let lastError: unknown = null;

  for (const candidate of candidates) {
    try {
      return await requestJson<T>(candidate.path, {
        method: candidate.method ?? "GET",
        body:
          candidate.body === undefined
            ? undefined
            : JSON.stringify(candidate.body),
      });
    } catch (error) {
      if (
        error instanceof ApiError &&
        FALLBACK_STATUSES.has(error.status ?? -1)
      ) {
        lastError = error;
        continue;
      }
      throw error;
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new ApiError("The requested API endpoint is not available.");
}

export function unwrapEntity(payload: unknown, keys: string[]): unknown {
  const record = asRecord(payload);
  for (const key of keys) {
    if (key in record) {
      return record[key];
    }
  }
  return payload;
}

export function normalizePlainObject(
  value: unknown,
): Record<string, unknown> | null {
  return isRecord(value) ? (value as Record<string, unknown>) : null;
}

export function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item: unknown) => String(item));
}
