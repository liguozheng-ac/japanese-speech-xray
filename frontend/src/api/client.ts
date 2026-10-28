import type { Prompt, SpeechXRayAnalysisResponse } from "./contract";
import schema from "../../../data/contracts/api-v1-analysis.schema.json";
import { validateContract } from "./validate";
import type { AnalysisProgress } from "./progress";
const base = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId = "",
    public reason = "",
  ) {
    super(message);
  }
}
async function request<T>(path: string, init?: RequestInit, onStart?: () => void): Promise<T> {
  let response: Response;
  try {
    onStart?.();
    response = await fetch(`${base}/api/v1${path}`, init);
  } catch {
    throw new ApiError(
      "NETWORK_ERROR",
      "连接中断，无法确认本次分析结果。请检查后端连接；不要在后端仍工作时重复提交。",
    );
  }
  let body;
  try { body = await response.json(); }
  catch { throw new ApiError("HTTP_ERROR", "本地服务返回了无法解析的内容，请检查服务状态。"); }
  if (!response.ok)
    throw new ApiError(
      body.error_code ?? "HTTP_ERROR",
      body.message ?? "请求失败",
      body.request_id,
      body.details?.reason_code,
    );
  return body as T;
}
export const loadPrompts = () =>
  request<{ prompt_pack_version: string; prompts: Prompt[] }>("/prompts");
export const readiness = () => request<{ status: string }>("/health/ready");
export async function analyze(
  promptId: string,
  blob: Blob,
  onStart?: () => void,
  controlToken?: string,
  signal?: AbortSignal,
): Promise<SpeechXRayAnalysisResponse> {
  const data = new FormData();
  data.append("prompt_id", promptId);
  data.append("audio", blob, "audio.wav");
  // The synchronous backend has a 900s deadline. Fetch has no short client timeout.
  const result = await request<SpeechXRayAnalysisResponse>("/analyses", {
    method: "POST",
    body: data,
    ...(controlToken ? { headers: { "X-Analysis-Token": controlToken } } : {}),
    ...(signal ? { signal } : {}),
  }, onStart);
  validateContract(result, schema, schema.$defs);
  return result;
}
export const cancelAnalysis = (token: string) => request<{ status: "NOT_FOUND" | "CANCELLING" | "CANCELLED" | "FINISHING" | "FINISHED" }>(`/analyses/cancel/${encodeURIComponent(token)}`, { method: "POST" });
export const analysisProgress = (token: string, signal: AbortSignal) => request<AnalysisProgress | {state: "NOT_FOUND"}>(`/analyses/progress/${encodeURIComponent(token)}`, { signal });
