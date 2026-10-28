import type { SpeechXRayAnalysisResponse, Target } from "../api/contract";

export type EvidenceSummary = {
  analysis_id: string;
  target: string;
  focus: { mora: string[]; phone: string[]; interval: Target["time_span"] };
  duration: Target["duration"];
  reference_relation: NonNullable<Target["deviation"]>["direction"] | null;
  realization: Target["realization"];
  availability: Target["availability"];
  warnings: string[];
  source_pointers: Record<string, string>;
};
export type Guidance = { focus: string; action: string; basis: string; source: string };
export function summarizeEvidence(response: SpeechXRayAnalysisResponse, t: Target): EvidenceSummary {
  const index = response.targets.indexOf(t), root = `/targets/${index}`;
  return {
    analysis_id: response.analysis_id, target: t.surface,
    focus: { mora: response.timeline?.morae.filter(m => t.mora_indices.includes(m.index)).map(m => m.representation) ?? [],
      phone: response.timeline?.phones.filter(p => p.word_index === t.word_index && t.time_span && p.start_ms >= t.time_span.start_ms && p.end_ms <= t.time_span.end_ms).map(p => p.symbol) ?? [], interval: t.time_span },
    duration: t.availability.duration ? t.duration : null,
    reference_relation: t.availability.duration && t.availability.reference && t.availability.deviation ? t.deviation?.direction ?? null : null,
    realization: t.availability.realization ? t.realization : null,
    availability: { ...t.availability }, warnings: [...response.warnings, ...t.reasons].map(r => r.reason_code),
    source_pointers: { target: root, duration: `${root}/duration`, relation: `${root}/deviation/direction`, realization: `${root}/realization`, availability: `${root}/availability` },
  };
}
export function guidanceFor(e: EvidenceSummary): Guidance[] {
  const result: Guidance[] = [];
  const relation = e.reference_relation;
  if (e.availability.duration && e.availability.reference && e.availability.deviation && e.duration && relation) {
    const wording = {
      BELOW_REFERENCE_MEDIAN: ["下一次可以尝试把目标长音保持得更完整，再与参考朗读比较。", "本次目标长音的语速归一化值位于参考中位数下方。"],
      ABOVE_REFERENCE_MEDIAN: ["可以结合参考朗读，再比较目标长音是否需要读得更紧凑。", "本次目标长音的语速归一化值位于参考中位数上方。"],
      AT_REFERENCE_MEDIAN: ["可以继续结合参考朗读，观察多次朗读是否保持稳定。", "本次目标长音持续特征位于参考分布中部附近。"],
    }[relation];
    result.push({ focus: "长音持续时间", action: wording[0], basis: wording[1], source: e.source_pointers.relation });
  }
  if (e.availability.realization && e.realization?.evidence_status === "AVAILABLE") {
    const variant = e.realization.selected_variant;
    if (variant === "CANONICAL_SELECTED" || variant === "REDUCED_SELECTED") {
      result.push({ focus: "长音实现方式", action: variant === "CANONICAL_SELECTED"
        ? "可以保持当前长音方式，并通过重复朗读观察稳定性。"
        : "下一次可以有意识地保持目标长音，并与参考朗读进行比较。",
        basis: `当前实验探针更支持${variant === "CANONICAL_SELECTED" ? "完整" : "简化"}候选实现。实验候选选择不是正确 / 错误判断。`, source: e.source_pointers.realization });
    }
  }
  return result;
}
