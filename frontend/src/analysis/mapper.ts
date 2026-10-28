import type {
  SpeechXRayAnalysisResponse,
  Target,
  TimeSpan,
} from "../api/contract";
export const seconds = (ms: number) => `${(ms / 1000).toFixed(2)} s`;
export const number = (n: number | null | undefined) =>
  n == null ? "当前证据不可用" : n.toFixed(3);
const statuses = {
  COMPLETED: "分析完成",
  PARTIAL_EVIDENCE: "部分证据可用",
  ABSTAINED: "当前无法形成足够证据",
};
export function targetEvidence(t: Target) {
  const realized = t.availability.realization && t.realization;
  return {
    target: t,
    duration:
      t.availability.duration && t.duration
        ? seconds(t.duration.raw_duration_ms)
        : "当前时长证据不可用",
    direction:
      t.availability.deviation && t.deviation
        ? {
            BELOW_REFERENCE_MEDIAN: "低于母语者参考中位数",
            AT_REFERENCE_MEDIAN: "位于母语者参考中位数",
            ABOVE_REFERENCE_MEDIAN: "高于母语者参考中位数",
          }[t.deviation.direction]
        : "当前参考位置不可用",
    realization: realized
      ? {
          CANONICAL_SELECTED: "当前实验探针更支持完整候选实现",
          REDUCED_SELECTED: "当前实验探针更支持简化候选实现",
          AMBIGUOUS_OR_UNRESOLVED: "实现候选尚未区分",
          ALIGNMENT_FAILED: "实现探针对齐未完成",
        }[realized.selected_variant]
      : t.reasons.some(r => r.reason_code === "REALIZATION_PROBE_NOT_AVAILABLE_WITH_NARABAS_V1")
        ? "当前版本暂不提供实现候选比较。" : "当前实现证据不可用",
  };
}
export function warningText(code: string) {
  return ({
    CROSS_SENTENCE_CONTEXT_NOT_VALIDATED: "目标词一致并不代表句子语境完全等价。",
    ALIGNMENT_UNUSABLE: "未能将这段录音与目标句子可靠对齐，无法生成发音时间结构或长音测量。",
  } as Record<string, string>)[code] ?? "当前证据存在限制，完整说明见技术细节。";
}
export function mapAnalysis(r: SpeechXRayAnalysisResponse) {
  return {
    id: r.analysis_id,
    sentence: r.prompt.display_text,
    status: statuses[r.status],
    targets: r.targets.map(targetEvidence),
    timeline: r.timeline,
    warnings: r.warnings,
    provenance: r.provenance,
    source: r,
  };
}
export type AnalysisViewModel = ReturnType<typeof mapAnalysis>;
export type Focus = {
  kind: "word" | "mora" | "phone";
  index: number;
  wordIndex: number | null;
  span: TimeSpan | null;
};
export function focusFor(
  vm: AnalysisViewModel,
  kind: Focus["kind"],
  index: number,
): Focus | null {
  const t = vm.timeline;
  if (!t) return null;
  if (kind === "word") {
    const w = t.words.find((w) => w.index === index);
    return w ? { kind, index, wordIndex: w.index, span: w } : null;
  }
  if (kind === "phone") {
    const p = t.phones.find((p) => p.index === index);
    return p ? { kind, index, wordIndex: p.word_index, span: p } : null;
  }
  const m = t.morae.find((m) => m.index === index);
  return m
    ? { kind, index, wordIndex: m.word_index, span: m.shared_span }
    : null;
}
export function overlaps(a: TimeSpan, b: TimeSpan) {
  return a.start_ms < b.end_ms && b.start_ms < a.end_ms;
}
