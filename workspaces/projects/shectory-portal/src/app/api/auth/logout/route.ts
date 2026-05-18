import { NextResponse } from "next/server";

export async function POST() {
  const secure = process.env.NODE_ENV === "production";
  const res = NextResponse.json({ ok: true });
  const clearAttrs = [
    "HttpOnly",
    "SameSite=Lax",
    "Max-Age=0",
    "Path=/",
    ...(secure ? ["Secure"] : []),
  ];
  res.headers.append("Set-Cookie", `shectory_portal_session=; ${clearAttrs.join("; ")}`);
  res.headers.append("Set-Cookie", `shectory_admin=; ${clearAttrs.join("; ")}`);
  return res;
}
