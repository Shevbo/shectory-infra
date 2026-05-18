import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PREFIXES = ["/login", "/_next/", "/brand/", "/favicon.ico"];
const PUBLIC_API_PREFIXES = ["/api/auth/", "/api/internal/"];

async function hmacSha256Hex(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const buf = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function verifyToken(token: string, secret: string): Promise<boolean> {
  const parts = token.split(":");
  if (parts.length < 3) return false;
  const sig = parts.at(-1)!;
  const expires = parts.at(-2)!;
  const email = parts.slice(0, -2).join(":");
  if (Math.floor(Date.now() / 1000) > parseInt(expires, 10)) return false;
  const payload = `${email}:${expires}`;
  const expected = await hmacSha256Hex(payload, secret);
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    PUBLIC_PREFIXES.some((p) => pathname.startsWith(p)) ||
    PUBLIC_API_PREFIXES.some((p) => pathname.startsWith(p))
  ) {
    return NextResponse.next();
  }

  const secret = process.env.AUTH_SESSION_SECRET?.trim();
  if (!secret) return NextResponse.next();

  const token = request.cookies.get("shectory_portal_session")?.value;
  if (!token || !(await verifyToken(token, secret))) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|brand/).*)"],
};
