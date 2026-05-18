import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { adminAuthOk } from "@/lib/admin-auth";

export async function GET(req: Request) {
  if (!(await adminAuthOk())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { searchParams } = new URL(req.url);
  const projectId = searchParams.get("projectId");
  if (!projectId) return NextResponse.json({ error: "projectId required" }, { status: 400 });

  const items = await prisma.backlogItem.findMany({
    where: { projectId },
    orderBy: [{ priority: "asc" }, { createdAt: "desc" }],
  });
  return NextResponse.json({ items });
}

export async function POST(req: Request) {
  if (!(await adminAuthOk())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: { projectId?: string; title?: string; description?: string; priority?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { projectId, title, description, priority } = body;
  if (!projectId || !title?.trim()) {
    return NextResponse.json({ error: "projectId and title required" }, { status: 400 });
  }
  const created = await prisma.backlogItem.create({
    data: {
      projectId,
      title: title.trim(),
      description: description?.trim() || null,
      priority: typeof priority === "number" ? priority : 3,
    },
  });
  return NextResponse.json({ item: created });
}
