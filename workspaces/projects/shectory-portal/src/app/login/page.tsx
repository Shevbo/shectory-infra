"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const j = await r.json().catch(() => ({} as { error?: string }));
      if (!r.ok) throw new Error((j as { error?: string }).error ?? "Ошибка входа");
      router.replace("/");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0f0f1e] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between mb-6">
          <img
            src="/brand/shectory-logo.gif"
            alt="Shectory"
            className="h-12 w-auto"
          />
          <div className="border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-bold text-white">
            PORTAL
          </div>
        </div>
        <div className="bg-[#14142a] border border-[#2d2d4a] rounded-xl p-6 flex flex-col gap-3">
          <h1 className="text-white font-semibold">Вход</h1>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <input
              type="email"
              className="w-full bg-[#0f0f1e] border border-[#2d2d4a] rounded px-3 py-2 text-[#ccc] text-sm outline-none focus:border-[#4a4a7a]"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
            <input
              type="password"
              className="w-full bg-[#0f0f1e] border border-[#2d2d4a] rounded px-3 py-2 text-[#ccc] text-sm outline-none focus:border-[#4a4a7a]"
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            {err && <p className="text-[#f66] text-xs">{err}</p>}
            <button
              type="submit"
              disabled={loading || !email.trim() || !password}
              className="w-full bg-[#2a6a2a] text-[#7fff7f] rounded px-3 py-2.5 text-sm font-medium disabled:opacity-50 hover:bg-[#3a8a3a] disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Вход..." : "Войти"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
