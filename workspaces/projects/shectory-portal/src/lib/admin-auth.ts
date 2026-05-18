import { cookies } from "next/headers";
import { verifySessionToken, SESSION_COOKIE } from "@/lib/portal-auth";

export async function adminAuthOk(): Promise<boolean> {
  const secret = process.env.AUTH_SESSION_SECRET?.trim();
  if (!secret) return true;
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return false;
  return verifySessionToken(token, secret) !== null;
}
