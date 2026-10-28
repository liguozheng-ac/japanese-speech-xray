import { validateCurves } from "./curves";
import type { Curves } from "./curves";
// Weak owners are session WAV blobs, never localStorage or a server learner cache.
const cache = new WeakMap<Blob, Map<string, Curves>>();
export const cachedCurves = (blob: Blob, prompt: string) => cache.get(blob)?.get(prompt) ?? null;

export async function extractCurves(blob: Blob, prompt: string, signal: AbortSignal): Promise<Curves> {
  cache.get(blob)?.delete(prompt);
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const sha = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, "0")).join("");
  const body = new FormData(); body.append("audio", blob, "prosody.wav"); body.append("prompt_id", prompt);
  const response = await fetch("/api/prosody/v1/curves", { method: "POST", body, signal });
  if (!response.ok) throw new Error(response.status === 503 ? "音高提取服务暂时忙碌，请稍后重试。" : `音高服务无法处理本次音频（HTTP ${response.status}）。原音仍可使用。`);
  const result = validateCurves(await response.json(), prompt, sha);
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  if (result.learner.status === "AVAILABLE") {
    const entries = cache.get(blob) ?? new Map<string, Curves>(); entries.set(prompt, result); cache.set(blob, entries);
  }
  return result;
}
