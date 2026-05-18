import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySessionToken, SESSION_COOKIE } from "@/lib/portal-auth";

export async function GET() {
  const secret = process.env.AUTH_SESSION_SECRET?.trim();
  if (!secret) return NextResponse.json({ ok: false }, { status: 401 });
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ ok: false }, { status: 401 });
  const email = verifySessionToken(token, secret);
  if (!email) return NextResponse.json({ ok: false }, { status: 401 });
  return NextResponse.json({ ok: true, email });
}
