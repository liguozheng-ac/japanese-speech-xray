import type { Prompt, SpeechXRayAnalysisResponse, TimeSpan } from "../api/contract";
import type { Phase, Turn } from "./state";

// Display metadata only; IDs/text are copied from the frozen learner-pilot-v1 pack.
// No phone generation or new server binding takes place here.
export const MVP_PROMPTS: Prompt[] = [
  { prompt_id: "learner-v1-001", display_text: "新しいスマートフォンを机に置きました。", prompt_version: "1" },
  { prompt_id: "learner-v1-002", display_text: "来月、舞台でデビューします。", prompt_version: "1" },
  { prompt_id: "learner-v1-003", display_text: "このシリーズを週末に見ます。", prompt_version: "1" },
];
export const PRACTICE = "可以先听参考发音，再尝试放慢语速，注意长元音持续发声的过程，之后重新录音比较。";
export const UNAVAILABLE = "当前无法可靠定位目标长元音。你仍然可以试听录音，并手动选择目标词区域进行练习。";
export const TARGETS: Record<string, { word: string; vowel: string; context: string; sentence: string }> = {
  "learner-v1-001": { word: "スマートフォン", vowel: "マー /aː/", context: "VOICEACTRESS100_010", sentence: "スマートフォンから、フィーチャーフォンまで、マルチデバイスに対応。" },
  "learner-v1-002": { word: "デビュー", vowel: "ビュー /uː/", context: "VOICEACTRESS100_051", sentence: "デビュー後の数年間は、ベビーフェイスとして、本名で活動。" },
  "learner-v1-003": { word: "シリーズ", vowel: "リー /iː/", context: "VOICEACTRESS100_074", sentence: "レジェンドシリーズをベースに、ヨーフリー機構を備えた、ビューカメラ。" },
};
export const validSpan = (s: TimeSpan | null | undefined, duration: number): s is TimeSpan =>
  !!s && [s.start_ms, s.end_ms, duration].every(Number.isFinite) && duration > 0 && s.start_ms >= 0 && s.end_ms > s.start_ms && s.end_ms <= duration;
export type UiEvidenceState = "INPUT_READY" | "RECORDING" | "AUDIO_READY" | "ANALYZING" | "EVIDENCE_AVAILABLE" | "EXPERIMENTAL_BOUNDARY" | "USER_SELECTION_AVAILABLE" | "ANALYSIS_UNAVAILABLE" | "ANALYSIS_FAILED";
export const inputEvidenceState = (phase: Phase, hasAudio: boolean): UiEvidenceState =>
  phase === "RECORDING" ? "RECORDING" : hasAudio ? "AUDIO_READY" : "INPUT_READY";

export function candidatesFor(response: SpeechXRayAnalysisResponse | undefined, promptId: string, duration: number) {
  const none = (reason: string) => ({ word: null, vowel: null, structureAvailable: false, reason } as {word: TimeSpan | null; vowel: TimeSpan | null; structureAvailable: boolean; reason: string});
  if (!response) return none("尚无自动分析结果");
  if (response.status === "ABSTAINED") return none("后端已弃权");
  if (response.prompt.prompt_id !== promptId || Math.abs(response.audio.duration_ms - duration) > 1)
    return none("分析身份或原始音频时间轴不匹配");
  if (response.provenance.alignment_engine !== "MFA_CPU_CLI") return none("非当前批准的 MFA 路径");
  const expected = TARGETS[promptId], timeline = response.timeline;
  if (!expected || !timeline || !timeline.words.length || !timeline.phones.length) return none("目标区域或音素序列缺失");
  if (![...timeline.words, ...timeline.phones].every(s => validSpan(s, duration))) return none("自动时间戳超出原始音频或无效");
  const target = response.targets.find(t => t.surface === expected.word);
  const word = target && timeline.words.find(w => w.index === target.word_index && w.surface === expected.word);
  if (!word) return none("没有可确认的目标词候选");
  const vowel = validSpan(target?.time_span, duration) && target!.time_span!.start_ms >= word.start_ms && target!.time_span!.end_ms <= word.end_ms
    ? target!.time_span : null;
  const moraeValid = timeline.morae.every(m => !m.shared_span || validSpan(m.shared_span, duration));
  return { word: { start_ms: word.start_ms, end_ms: word.end_ms }, vowel, structureAvailable: !!vowel && moraeValid,
    reason: vowel ? "自动边界仍处于实验验证阶段" : "长元音候选缺失或不在目标词内" };
}
export function turnEvidenceState(t: Turn): UiEvidenceState {
  if (t.status === "ANALYZING" || t.status === "QUEUED") return "ANALYZING";
  if (t.status === "CANCELLED" || t.status === "ABSTAINED") return "ANALYSIS_UNAVAILABLE";
  if (t.status === "ERROR") return ["NETWORK_ERROR", "HTTP_ERROR", "SERVICE_BUSY", "ALIGNMENT_RUNTIME_UNAVAILABLE", "REFERENCE_ARTIFACT_MISSING", "ANALYSIS_TIMEOUT"].includes(t.errorCode ?? "") ? "ANALYSIS_UNAVAILABLE" : "ANALYSIS_FAILED";
  const c = candidatesFor(t.response, t.prompt.prompt_id, t.audio.durationMs);
  return c.word ? "EXPERIMENTAL_BOUNDARY" : "USER_SELECTION_AVAILABLE";
}
export function analysisError(code: string) {
  return ({
    NETWORK_ERROR: "本地分析服务无法连接或连接已中断。原始音频仍可试听和手动框选；服务端状态尚未确认，请不要重复提交。",
    HTTP_ERROR: "本地分析服务暂时没有返回有效结果。原始音频仍可用于手动练习。",
    ALIGNMENT_RUNTIME_UNAVAILABLE: "自动对齐服务当前不可用。请保留原音，先使用手动区域选择练习。",
    REFERENCE_ARTIFACT_MISSING: "研究参考资源当前不可用，不影响原音和手动试听。",
    ANALYSIS_TIMEOUT: "自动分析超时，未取得可用结果。你仍可手动选择和试听原音。",
    SERVICE_BUSY: "本地后端仍在处理其他任务，暂时不能开始本次分析。",
    ANALYSIS_CANCELLED: "分析已取消。",
    INVALID_AUDIO: "音频无法用于本次分析，请检查 WAV 格式。",
    INTERNAL_PIPELINE_ERROR: "自动分析处理失败。请使用原音与手动选区练习，或稍后重新尝试。",
  } as Record<string, string>)[code] ?? "本次自动分析没有得到可用结果。原音仍可试听，技术原因见展开说明。";
}
