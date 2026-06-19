import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { askLLM } from "@/lib/llm";
import { adminAuthOk } from "@/lib/admin-auth";

// Сколько последних сообщений сессии подаём как контекст диалога.
const HISTORY_LIMIT = 12;

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

  const history = await prisma.chatMessage.findMany({
    where: { sessionId },
    orderBy: { createdAt: "desc" },
    take: HISTORY_LIMIT,
  });
  history.reverse();

  const userMsg = await prisma.chatMessage.create({
    data: { sessionId, role: "user", content: message.trim() },
  });

  const prompt = buildPrompt(
    {
      name: project.name,
      description: project.description,
      aiContext: project.aiContext,
      workspacePath: project.workspacePath,
    },
    history,
    message.trim()
  );

  const res = await askLLM(prompt);
  const reply =
    (res.ok ? res.text : "").trim() ||
    `(LLM не ответил${res.error ? `: ${res.error}` : ""}. Проверьте Lineman /api/klod/ask на :9090)`;

  const assistantMsg = await prisma.chatMessage.create({
    data: { sessionId, role: "assistant", content: reply },
  });

  return NextResponse.json({
    ok: res.ok,
    reply,
    model: res.model,
    provider: res.provider,
    userMsg,
    assistantMsg,
  });
}

function buildPrompt(
  project: { name: string; description: string; aiContext: string; workspacePath: string },
  history: { role: string; content: string }[],
  latest: string
): string {
  const sys = [
    `Ты технический ассистент платформы Shectory. Отвечаешь по проекту «${project.name}».`,
    `Рабочий каталог проекта: ${project.workspacePath}.`,
    `Отвечай на русском, по делу, без воды. Если данных недостаточно — скажи об этом.`,
    "",
    "## Описание проекта",
    project.description || "(нет)",
    "",
    "## Контекст для ИИ (архитектура / инженерия)",
    project.aiContext || "(нет)",
  ].join("\n");

  const dialog = history
    .filter((m) => m.content.trim())
    .map((m) => `${m.role === "user" ? "Пользователь" : "Ассистент"}: ${m.content}`)
    .join("\n");

  return [
    sys,
    "",
    "## Диалог",
    dialog || "(начало диалога)",
    `Пользователь: ${latest}`,
    "Ассистент:",
  ].join("\n");
}
