import { createHmac, timingSafeEqual as nodeTimingSafeEqual } from "node:crypto";
import bcrypt from "bcryptjs";
import { prisma } from "@/lib/prisma";

const SESSION_TTL = 60 * 60 * 24 * 30; // 30 days in seconds
export const SESSION_COOKIE = "shectory_portal_session";

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

function timingSafeEqualStr(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  return nodeTimingSafeEqual(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

export function makeSessionToken(email: string, secret: string): string {
  const expires = Math.floor(Date.now() / 1000) + SESSION_TTL;
  const payload = `${email}:${expires}`;
  return `${payload}:${sign(payload, secret)}`;
}

export function verifySessionToken(token: string, secret: string): string | null {
  const parts = token.split(":");
  if (parts.length < 3) return null;
  const sig = parts.at(-1)!;
  const expires = parts.at(-2)!;
  const email = parts.slice(0, -2).join(":");
  const payload = `${email}:${expires}`;
  if (!timingSafeEqualStr(sig, sign(payload, secret))) return null;
  if (Math.floor(Date.now() / 1000) >= parseInt(expires, 10)) return null;
  return email;
}

export async function verifyPortalCredentials(
  email: string,
  password: string
): Promise<{ email: string; role: string; fullName: string } | null> {
  const emailNorm = email.trim().toLowerCase();
  const user = await prisma.portalUser.findUnique({ where: { email: emailNorm } });
  if (!user || !user.passwordHash) return null;
  const ok = await bcrypt.compare(password, user.passwordHash);
  if (!ok) return null;
  return {
    email: user.email,
    role: user.role,
    fullName: user.fullName ?? "",
  };
}

export function makeSessionCookieHeader(token: string, secure: boolean): string {
  const attrs = [
    `${SESSION_COOKIE}=${encodeURIComponent(token)}`,
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${SESSION_TTL}`,
    "Path=/",
    ...(secure ? ["Secure"] : []),
  ];
  return attrs.join("; ");
}
