import type { TimeSpan } from "../api/contract";
export type SelectionKind = "word" | "vowel";
export type AudioSelection = { word: TimeSpan | null; vowel: TimeSpan | null; wordConfirmed: boolean };
export const emptySelection: AudioSelection = { word: null, vowel: null, wordConfirmed: false };
// Adapted from R2 boundary_annotation/player.js: original-time coordinates only.
export const timeAt = (x: number, width: number, duration: number) => Math.max(0, Math.min(1, x / width)) * duration;
export function selectionFrom(a: number, b: number, duration: number): TimeSpan {
  if (![a, b, duration].every(Number.isFinite) || duration <= 0) throw new Error("选区时间无效。");
  const start_ms = Math.max(0, Math.min(a, b)), end_ms = Math.min(duration, Math.max(a, b));
  if (end_ms <= start_ms) throw new Error("请拖动选择一个非空区间。");
  return { start_ms, end_ms };
}
export function updateSelection(s: AudioSelection, kind: SelectionKind, span: TimeSpan | null): AudioSelection {
  return { ...s, [kind]: span && { ...span }, wordConfirmed: kind === "word" ? false : s.wordConfirmed };
}
export function selectionStatus(s: AudioSelection): string[] {
  return [s.wordConfirmed && s.word ? "WORD_REGION_USER_CONFIRMED" : null, s.vowel ? "VOWEL_REGION_USER_SELECTED" : null].filter((s): s is string => !!s);
}
