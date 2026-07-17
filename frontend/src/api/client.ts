export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies must set their own multipart boundary — no explicit Content-Type.
  const jsonHeaders: Record<string, string> =
    init?.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const resp = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    headers: { ...jsonHeaders, ...init?.headers },
    ...init,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body: keep statusText
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
