import { NextResponse } from "next/server";
import {
  makeSessionToken,
  makeSessionCookieHeader,
  verifyPortalCredentials,
} from "@/lib/portal-auth";

export async function POST(req: Request) {
  const secret = process.env.AUTH_SESSION_SECRET?.trim();
  if (!secret) {
    return NextResponse.json({ error: "AUTH_SESSION_SECRET not configured" }, { status: 503 });
  }

  let body: { email?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = String(body.email ?? "").trim().toLowerCase();
  const password = String(body.password ?? "");

  if (!email || !password) {
    return NextResponse.json({ error: "email и password обязательны" }, { status: 400 });
  }

  const user = await verifyPortalCredentials(email, password);
  if (!user) {
    return NextResponse.json({ error: "Неверный email или пароль" }, { status: 401 });
  }

  const token = makeSessionToken(user.email, secret);
  const secure = process.env.NODE_ENV === "production";
  const res = NextResponse.json({ ok: true, email: user.email, role: user.role });
  res.headers.set("Set-Cookie", makeSessionCookieHeader(token, secure));
  return res;
}
