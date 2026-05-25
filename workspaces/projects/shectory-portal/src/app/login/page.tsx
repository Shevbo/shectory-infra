"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

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

  const inputStyle: React.CSSProperties = {
    width: "100%", border: "1px solid #223252", borderRadius: "8px",
    background: "#0d1525", color: "#e8efff", padding: "10px",
    fontSize: "14px", outline: "none", boxSizing: "border-box", marginTop: "6px",
  };

  return (
    <main style={{ minHeight: "100vh", padding: "20px", background: "radial-gradient(circle at top, #16223c 0%, #0b1220 55%)", color: "#e8efff", fontFamily: "Inter, Arial, sans-serif", boxSizing: "border-box" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", marginBottom: "16px" }}>
        <div style={{ border: "1px solid #223252", background: "#0f182a", borderRadius: "10px", padding: "6px 12px" }}>
          <img src="/brand/shectory-logo.gif" alt="Shectory" style={{ height: "64px", width: "auto", display: "block" }} />
        </div>
        <div style={{ display: "grid", justifyItems: "end", gap: "6px" }}>
          <div style={{ border: "1px solid #223252", background: "#0f182a", borderRadius: "10px", padding: "10px 12px", fontWeight: 700, fontSize: "14px" }}>Shectory Portal</div>
          <div style={{ color: "#8fa3c6", fontSize: "12px" }}>Единый каталог пользователей</div>
        </div>
      </header>
      <section style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "16px" }}>
        <article style={{ border: "1px solid #223252", borderRadius: "12px", background: "#121a2b", padding: "18px", minHeight: "68vh" }}>
          <h1 style={{ margin: "0 0 8px", fontSize: "1.4rem" }}>Вход в Shectory Portal</h1>
          <p style={{ color: "#8fa3c6", margin: "0.45rem 0" }}>Управление проектами, бэклогом и деплоем.</p>
          <p style={{ color: "#8fa3c6", margin: "0.45rem 0" }}>Единый аккаунт работает во всех приложениях Shectory.</p>
          <p style={{ color: "#8fa3c6", margin: "0.45rem 0" }}>Пароли хранятся только как bcrypt-хэши.</p>
        </article>
        <aside style={{ border: "1px solid #223252", borderRadius: "12px", background: "#121a2b", padding: "18px" }}>
          <h2 style={{ margin: "0 0 8px", fontSize: "1.1rem" }}>Вход</h2>
          {err && <div style={{ color: "#fca5a5", background: "#31243a", border: "1px solid #5b2133", padding: "0.6rem 0.7rem", borderRadius: "10px", fontSize: "0.9rem", marginBottom: "10px" }}>{err}</div>}
          <div style={{ margin: "0.8rem 0 0.3rem", padding: "0.6rem 0.7rem", border: "1px solid #223252", borderRadius: "10px", color: "#8fa3c6", fontSize: "0.9rem" }}>
            Используется единый каталог пользователей Shectory.
          </div>
          <form onSubmit={submit} style={{ display: "grid", gap: "10px", marginTop: "10px" }}>
            <label htmlFor="login-email" style={{ display: "block", fontSize: "0.9rem", color: "#dbe6ff" }}>E-mail</label>
            <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete="username" autoFocus required disabled={loading} style={inputStyle} />
            <label htmlFor="login-password" style={{ display: "block", fontSize: "0.9rem", color: "#dbe6ff" }}>Пароль</label>
            <input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" required disabled={loading} style={inputStyle} />
            <button type="submit" disabled={loading || !email.trim() || !password}
              style={{ marginTop: "6px", border: 0, borderRadius: "8px", padding: "10px 12px", background: "#4f8cff", color: "#fff", fontWeight: 700, cursor: "pointer", fontSize: "14px", opacity: (loading || !email.trim() || !password) ? 0.5 : 1 }}>
              {loading ? "Вход..." : "Войти"}
            </button>
          </form>
          <p style={{ color: "#8fa3c6", marginTop: "10px", fontSize: "0.9rem" }}>
            <Link href="/forgot-password" style={{ color: "#9ec1ff", textDecoration: "none" }}>Забыл пароль?</Link>
          </p>
          <p style={{ marginTop: "0.9rem", fontSize: "0.84rem", color: "#8fa3c6" }}>
            Поддержка: <a href="mailto:support@shectory.ru" style={{ color: "#9ec1ff", textDecoration: "none" }}>support@shectory.ru</a>
          </p>
        </aside>
      </section>
    </main>
  );
}
