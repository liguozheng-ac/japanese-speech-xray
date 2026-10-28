export const STAGES = ["音频准备", "主发音对齐", "声学证据与参考计算", "实现候选比较", "结果整理"] as const;
export type AnalysisProgress = { state: "RUNNING" | "FINISHED" | "ERROR" | "CANCELLED"; request_key: string; request_id: string; stage_index: number; stage_label: string; updated_at: string; history: {stage_index: number; stage_label: string; updated_at: string}[] };
