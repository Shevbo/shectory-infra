import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { runAgentPrompt } from "@/lib/agent";
import { adminAuthOk } from "@/lib/admin-auth";

export async function POST(req: Request) {
  if (!(await adminAuthOk())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { projectId?: string; sessionId?: string; message?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const { projectId, sessionId, message } = body;
  if (!projectId || !sessionId || !message?.trim()) {
    return NextResponse.json({ error: "projectId, sessionId, message required" }, { status: 400 });
  }

  const project = await prisma.project.findUnique({ where: { id: projectId } });
  if (!project) return NextResponse.json({ error: "Project not found" }, { status: 404 });
  const session = await prisma.chatSession.findFirst({
    where: { id: sessionId, projectId },
  });
  if (!session) return NextResponse.json({ error: "Session not found" }, { status: 404 });

  const userMsg = await prisma.chatMessage.create({
    data: { sessionId, role: "user", content: message.trim() },
  });

  const { ok, stdout, stderr } = await runAgentPrompt(project.workspacePath, message.trim());
  const reply =
    (ok ? stdout : stderr || stdout).trim() ||
    "(пустой ответ agent; проверьте CURSOR_API_KEY и путь workspace)";

  const assistantMsg = await prisma.chatMessage.create({
    data: { sessionId, role: "assistant", content: reply },
  });

  return NextResponse.json({
    ok,
    reply,
    userMsg,
    assistantMsg,
  });
}
