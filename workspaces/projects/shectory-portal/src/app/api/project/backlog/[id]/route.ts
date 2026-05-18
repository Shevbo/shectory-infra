import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { adminAuthOk } from "@/lib/admin-auth";

type Ctx = { params: { id: string } };

export async function PATCH(req: Request, { params }: Ctx) {
  if (!(await adminAuthOk())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { status?: string; priority?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const updated = await prisma.backlogItem.update({
    where: { id: params.id },
    data: {
      status: body.status,
      priority: body.priority,
    },
  });
  return NextResponse.json({ item: updated });
}
