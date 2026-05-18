import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { adminAuthOk } from "@/lib/admin-auth";

export async function GET(req: Request) {
  if (!(await adminAuthOk())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { searchParams } = new URL(req.url);
  const projectId = searchParams.get("projectId");
  if (!projectId) return NextResponse.json({ error: "projectId required" }, { status: 400 });

  const [modules, testCases] = await Promise.all([
    prisma.testModule.findMany({ where: { projectId }, orderBy: { name: "asc" } }),
    prisma.testCase.findMany({
      where: { projectId },
      include: { module: true },
      orderBy: { createdAt: "desc" },
    }),
  ]);
  return NextResponse.json({ modules, testCases });
}

export async function POST(req: Request) {
  if (!(await adminAuthOk())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  let body: {
    projectId?: string;
    moduleName?: string;
    title?: string;
    description?: string;
    kind?: string;
    scope?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { projectId, moduleName, title, description, kind, scope } = body;
  if (!projectId || !title?.trim()) {
    return NextResponse.json({ error: "projectId and title required" }, { status: 400 });
  }
  let moduleId: string | null = null;
  if (moduleName?.trim()) {
    const mod = await prisma.testModule.upsert({
      where: { projectId_name: { projectId, name: moduleName.trim() } },
      create: { projectId, name: moduleName.trim() },
      update: {},
    });
    moduleId = mod.id;
  }
  const tc = await prisma.testCase.create({
    data: {
      projectId,
      moduleId,
      title: title.trim(),
      description: description?.trim() || "",
      kind: kind?.trim() || "manual-guided",
      scope: scope?.trim() || "ui",
    },
    include: { module: true },
  });
  return NextResponse.json({ testCase: tc });
}
