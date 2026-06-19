// LLM-доступ портала строго через Klod-gateway Lineman (политика Бори 2026-06-18).
// Портал не ходит в /proxy/deepseek напрямую — только POST /api/klod/ask.
// Модель deepseek flash резолвится по model_hint="deepseek-fast" (→ deepseek-chat).

const LINEMAN_URL = process.env.LINEMAN_URL ?? "http://127.0.0.1:9090";
const KLOD_AGENT = process.env.KLOD_AGENT ?? "portal";
const DEFAULT_MODEL_HINT = process.env.KLOD_MODEL_HINT ?? "deepseek-fast";

export type KlodAskResult = {
  ok: boolean;
  text: string;
  model?: string;
  provider?: string;
  elapsedMs?: number;
  error?: string;
};

export async function askLLM(
  prompt: string,
  opts: { modelHint?: string; maxTokens?: number; timeoutMs?: number } = {}
): Promise<KlodAskResult> {
  const modelHint = opts.modelHint ?? DEFAULT_MODEL_HINT;
  const maxTokens = opts.maxTokens ?? 2000;
  const timeoutMs = opts.timeoutMs ?? 120000;

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(`${LINEMAN_URL}/api/klod/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent: KLOD_AGENT,
        prompt,
        model_hint: modelHint,
        max_tokens: maxTokens,
      }),
      signal: ctrl.signal,
    });
    const j = (await r.json().catch(() => ({}))) as Record<string, unknown>;
    if (!r.ok) {
      return {
        ok: false,
        text: "",
        error: String(j.error ?? j.reason ?? `Lineman ${r.status}`),
      };
    }
    return {
      ok: true,
      text: String(j.text ?? ""),
      model: typeof j.model_used === "string" ? j.model_used : undefined,
      provider: typeof j.provider === "string" ? j.provider : undefined,
      elapsedMs: typeof j.elapsed_ms === "number" ? j.elapsed_ms : undefined,
    };
  } catch (e) {
    const msg = e instanceof Error && e.name === "AbortError" ? "timeout" : String(e);
    return { ok: false, text: "", error: msg };
  } finally {
    clearTimeout(t);
  }
}
