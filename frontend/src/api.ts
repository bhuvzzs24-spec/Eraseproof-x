export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch("/api" + path, {
      ...options,
      credentials: "same-origin",
      signal: signal
        ? AbortSignal.any([signal, controller.signal])
        : controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        response.status || 502,
        "The server returned an unreadable response.",
      );
    }
    if (!response.ok) {
      if (
        response.status === 401 &&
        path !== "/session" &&
        typeof window !== "undefined"
      )
        window.dispatchEvent(new Event("eraseproof-session-expired"));
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? String(body.detail)
          : "Request failed";
      throw new ApiError(response.status, detail);
    }
    if (body === null || typeof body !== "object")
      throw new ApiError(502, "Unexpected API response shape");
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) throw error;
    throw new ApiError(
      controller.signal.aborted ? 504 : 503,
      controller.signal.aborted
        ? "Request timed out. Refresh to inspect the actual outcome."
        : "Connection unavailable. No successful outcome has been assumed.",
    );
  } finally {
    clearTimeout(timer);
  }
}
export function mutation<T>(path: string, body: unknown, csrf: string) {
  return api<T>(path, {
    method: "POST",
    headers: { "X-CSRF-Token": csrf },
    body: JSON.stringify(body),
  });
}
export function download(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function outcome(value: string) {
  const labels: Record<string, [string, string]> = {
    VERIFIED_ABSENT: ["Verified absent · scoped", "good"],
    FALSE_SUCCESS_DETECTED: ["False success detected", "danger"],
    RESIDUAL_DATA_DETECTED: ["Residual data detected", "danger"],
    PENDING_CONSISTENCY: ["Pending consistency", "pending"],
    INCONCLUSIVE: ["Inconclusive", "warn"],
    UNSUPPORTED: ["Unsupported scope", "muted"],
    COMPLETED_REPORTED: ["Completed reported", "reported"],
    PARTIALLY_FAILED: ["Partially failed", "warn"],
    FAILED: ["Failed", "danger"],
    COMPLETED: ["Completed", "good"],
    FINISHED: ["Finished", "reported"],
    ACTIVE: ["Active source", "reported"],
    DELETED: ["Deletion lifecycle ended", "muted"],
    DELETING: ["Deleting", "pending"],
    REQUESTED: ["Requested", "pending"],
    IN_PROGRESS: ["In progress", "pending"],
    RETRYING: ["Retrying", "warn"],
    WAITING: ["Waiting", "pending"],
    RUNNING: ["Running", "pending"],
    QUEUED: ["Queued", "pending"],
    ready: ["Ready", "good"],
    unavailable: ["Unavailable", "danger"],
    SUCCEEDED_REPORTED: ["Success reported", "reported"],
    FAILED_TERMINAL: ["Terminal failure", "danger"],
    RETRY_WAIT: ["Retry scheduled", "warn"],
    ABSENT: ["Absent · oracle", "good"],
    RESIDUAL: ["Residual · oracle", "danger"],
    UNAVAILABLE: ["Unavailable · oracle", "warn"],
    PENDING: ["Pending", "pending"],
    INTERRUPTED: ["Interrupted", "warn"],
    TIMED_OUT: ["Timed out", "warn"],
  };
  return labels[value] || [value.replaceAll("_", " ").toLowerCase(), "muted"];
}
export function percentage(value: number | null) {
  return value === null ? "Undefined" : `${(value * 100).toFixed(1)}%`;
}
export function date(value: string | number | null | undefined) {
  return value
    ? new Date(typeof value === "number" ? value * 1000 : value).toLocaleString(
        undefined,
        {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        },
      )
    : "Not observed";
}
export function short(value: string) {
  return value.slice(0, 8);
}
