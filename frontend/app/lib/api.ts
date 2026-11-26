export class ApiFailure extends Error {
  constructor(message: string, public code: string, public retryable: boolean) { super(message); }
}

export async function api<T>(path: string, method = "GET", body?: Record<string, unknown>): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    response = await fetch(`/api/${path}`, { method, headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined, cache: "no-store", signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new ApiFailure(data.message || "Không thực hiện được yêu cầu.", data.code || "unknown", Boolean(data.retryable));
    return data;
  } catch (error) {
    if (error instanceof ApiFailure) throw error;
    throw new ApiFailure("Kết nối bị gián đoạn. Bài đang viết được giữ lại; thử lại cùng yêu cầu.", "network_unavailable", true);
  } finally { clearTimeout(timeout); }
}
