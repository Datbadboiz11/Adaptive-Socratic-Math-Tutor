import { NextRequest, NextResponse } from "next/server";

const allowed = /^(demo\/(profiles|login)|me|topics|sessions(\/[0-9a-fA-F-]{36}(\/(draft|turns|pause|resume|next|finish|report))?)?)$/;
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = path.join("/");
  if (!allowed.test(target)) return NextResponse.json({ message: "Không tìm thấy API." }, { status: 404 });
  try {
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    if (!origin || !URL.canParse(origin) || new URL(origin).host !== request.headers.get("host")) return NextResponse.json({ message: "Yêu cầu khác nguồn bị từ chối." }, { status: 403 });
  }
    const token = request.cookies.get("mo_demo")?.value;
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && body.length > 20000) return NextResponse.json({ message: "Nội dung quá dài." }, { status: 413 });
    const response = await fetch(`${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/v1/${target}`, {
      method: request.method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body, cache: "no-store", signal: AbortSignal.timeout(30000),
    });
    const data = await response.json();
    if (target === "demo/login" && response.ok) {
      const output = NextResponse.json({ profile: data.profile, mode: data.mode });
      output.cookies.set("mo_demo", data.access_token, { httpOnly: true, sameSite: "strict", secure: request.nextUrl.protocol === "https:", path: "/", maxAge: 86400 });
      output.headers.set("Cache-Control", "no-store");
      return output;
    }
    return NextResponse.json(data, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ code: "network_unavailable", message: "Chưa nhận được phản hồi. Giữ bài làm và thử lại yêu cầu.", retryable: true }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
