import manifest from "../../public/demo/manifest.json";
import schema from "../../../data/contracts/api-v1-analysis.schema.json";
import { validateContract } from "../api/validate";
import type { SpeechXRayAnalysisResponse } from "../api/contract";
import { MVP_PROMPTS, TARGETS, candidatesFor } from "../analysis/mvp";
import { parseWav } from "../audio/wav";
import { validateCurves } from "../prosody/curves";

export const DEMOS = MVP_PROMPTS.map(prompt => ({ prompt, label: TARGETS[prompt.prompt_id].word }));
export function demoFromHash(hash: string): string | null {
  if (hash.split("?")[0] !== "#/workspace") return null;
  const id = new URLSearchParams(hash.split("?")[1]).get("demo");
  return DEMOS.some(d => d.prompt.prompt_id === id) ? id : null;
}
const sha256 = async (bytes: ArrayBuffer) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");

/** Fixed synthetic assets and immutable service receipts; never submits audio. */
export async function loadDemo(promptId: string, signal: AbortSignal, get: typeof fetch = fetch) {
  const entry = manifest.cases.find(c => c.prompt_id === promptId);
  const prompt = MVP_PROMPTS.find(p => p.prompt_id === promptId);
  if (!entry || !prompt) throw new Error("未找到这条 DEMO。");
  const base = import.meta.env.BASE_URL;
  const paths = [`audio/reference/${promptId}.wav`, `demo/${promptId}-analysis.json`, `demo/${promptId}-prosody.json`];
  const bytes = await Promise.all(paths.map(async path => {
    const response = await get(`${base}${path}`, { signal });
    if (!response.ok) throw new Error("DEMO 文件暂时无法读取，请重试。");
    return response.arrayBuffer();
  }));
  signal.throwIfAborted();
  const hashes = await Promise.all(bytes.map(sha256));
  if (hashes.some((hash, i) => hash !== [entry.audio_sha256, entry.analysis_sha256, entry.prosody_sha256][i]))
    throw new Error("DEMO 文件校验失败，未展示不匹配的音频或结果。");
  const wav = parseWav(bytes[0]);
  const decode = (buffer: ArrayBuffer) => JSON.parse(new TextDecoder().decode(buffer));
  const raw: unknown = decode(bytes[1]);
  validateContract(raw, schema, schema.$defs);
  const response = raw as SpeechXRayAnalysisResponse;
  if (response.status !== "COMPLETED" || response.prompt.prompt_id !== promptId || response.prompt.display_text !== prompt.display_text ||
      response.audio.sha256 !== hashes[0] || response.audio.channels !== 1 || response.audio.sample_rate_hz !== wav.sampleRate ||
      response.audio.sample_count !== wav.samples.length || Math.abs(response.audio.duration_ms - wav.durationMs) > .001 ||
      !candidatesFor(response, promptId, wav.durationMs).structureAvailable)
    throw new Error("DEMO 分析与原音、句子或时间轴不一致，已停止展示。");
  const curves = validateCurves(decode(bytes[2]), promptId, hashes[0]);
  if (curves.learner.sample_count !== wav.samples.length || curves.learner.sample_rate_hz !== wav.sampleRate ||
      curves.reference_source?.sha256 !== hashes[0] || curves.reference_source.text !== prompt.display_text || curves.reference?.audio_sha256 !== hashes[0])
    throw new Error("DEMO 音高与同句合成参考不匹配，已停止展示。");
  signal.throwIfAborted();
  return { prompt, response, curves, audio: { ...wav, blob: new Blob([bytes[0]], { type: "audio/wav" }), name: `${promptId}-haruka-demo.wav` } };
}
