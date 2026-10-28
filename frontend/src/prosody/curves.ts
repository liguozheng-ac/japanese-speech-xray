/** Descriptive pitch only. Original seconds; never align words or score accent. */
export type Frame = { time_ms: number; f0_hz: number | null; voiced: boolean; pyin_voiced: boolean | null; voiced_probability: number | null; rms_dbfs: number };
export type Track = {
  status: "AVAILABLE" | "ABSTAINED"; reason: string | null; audio_sha256: string;
  duration_ms: number; sample_rate_hz: number; sample_count: number;
  parameters: Record<string, unknown>; frames: Frame[]; extraction_ms: number;
  observations: null | { median_f0_hz: number; p10_f0_hz: number; p90_f0_hz: number; voiced_fraction: number; median_voiced_probability: number; late_minus_early_semitones: number | null };
};
export type Curves = {
  schema_version: "prosody-1.0"; algorithm: string; prompt_id: string; learner: Track;
  reference: Track | null; reference_reason: string | null; total_ms: number;
  reference_source: null | { prompt_id: string; type: "synthetic"; voice: string; engine: string; text: string; sha256: string; path: string; label: string };
};
export type PitchUnit = "hz" | "semitones";
export const SEMITONE_METHOD = "12 × log₂(F0 / 本段有效有声帧 F0 中位数)";
const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

export function validateCurves(value: unknown, promptId: string, sha: string): Curves {
  const row = value as Curves;
  const trackValid = (t: Track) => t && ["AVAILABLE", "ABSTAINED"].includes(t.status) && finite(t.duration_ms) && t.duration_ms > 0 && t.duration_ms <= 30000 &&
    finite(t.sample_rate_hz) && t.sample_rate_hz >= 8000 && t.sample_rate_hz <= 48000 && Number.isInteger(t.sample_count) && t.sample_count > 0 && Math.abs(t.duration_ms - t.sample_count / t.sample_rate_hz * 1000) < .001 && finite(t.extraction_ms) && /^[a-f0-9]{64}$/.test(t.audio_sha256) &&
    Array.isArray(t.frames) && t.frames.length <= 1600 && t.frames.every((f, i) => finite(f.time_ms) && f.time_ms >= 0 && f.time_ms < t.duration_ms &&
      (!i || f.time_ms > t.frames[i - 1].time_ms) && typeof f.voiced === "boolean" && finite(f.rms_dbfs) &&
      (f.voiced_probability === null || (finite(f.voiced_probability) && f.voiced_probability >= 0 && f.voiced_probability <= 1)) &&
      (f.voiced ? finite(f.f0_hz) && f.f0_hz >= 50 && f.f0_hz <= 600 && f.voiced_probability !== null && t.status === "AVAILABLE" : f.f0_hz === null)) &&
    (t.status === "ABSTAINED" ? t.observations === null : t.frames.filter(f => f.voiced).length >= 5 && t.observations && finite(t.observations.median_f0_hz) && t.observations.median_f0_hz >= 50 && t.observations.median_f0_hz <= 600 &&
      finite(t.observations.p10_f0_hz) && finite(t.observations.p90_f0_hz) && finite(t.observations.voiced_fraction) && finite(t.observations.median_voiced_probability) &&
      (t.observations.late_minus_early_semitones === null || finite(t.observations.late_minus_early_semitones)));
  if (!row || row.schema_version !== "prosody-1.0" || row.algorithm !== "prosody-pyin-1" || row.prompt_id !== promptId || !finite(row.total_ms) || !trackValid(row.learner) || row.learner.audio_sha256 !== sha ||
      (row.reference !== null && (!trackValid(row.reference) || !row.reference_source || row.reference_source.prompt_id !== promptId || row.reference_source.type !== "synthetic" || row.reference_source.voice !== "Microsoft Haruka Desktop" || row.reference_source.sha256 !== row.reference.audio_sha256)))
    throw new Error("音高结果与本次音频不匹配或数据无效。原音和手动练习仍可使用。");
  return row;
}

export function pitchValue(frame: Frame, track: Track, unit: PitchUnit): number | null {
  if (track.status !== "AVAILABLE" || !frame.voiced || frame.f0_hz === null) return null;
  const median = track.observations?.median_f0_hz;
  return unit === "hz" ? frame.f0_hz : median ? 12 * Math.log2(frame.f0_hz / median) : null;
}

export function segments(track: Track, unit: PitchUnit) {
  const out: { weak: boolean; points: { time: number; value: number }[] }[] = [];
  let active: typeof out[number] | null = null;
  for (const frame of track.frames) {
    const value = pitchValue(frame, track, unit);
    if (value === null) { active = null; continue; }
    const weak = (frame.voiced_probability ?? 0) < .5;
    if (!active || active.weak !== weak) { active = { weak, points: [] }; out.push(active); }
    active.points.push({ time: frame.time_ms, value });
  }
  return out;
}

export function pitchDomain(tracks: Track[], unit: PitchUnit): [number, number] {
  const values = tracks.flatMap(t => t.frames.map(f => pitchValue(f, t, unit)).filter((n): n is number => n !== null));
  if (!values.length) return unit === "hz" ? [50, 600] : [-6, 6];
  const lo = Math.min(...values), hi = Math.max(...values);
  if (unit === "semitones") { const limit = Math.max(4, Math.ceil(Math.max(Math.abs(lo), Math.abs(hi)) + 1)); return [-limit, limit]; }
  return [Math.max(50, Math.floor((lo - 20) / 50) * 50), Math.min(600, Math.ceil((hi + 20) / 50) * 50)];
}

export const reasons: Record<string, string> = {
  AUDIO_TOO_SHORT_FOR_F0: "音频过短，无法可靠提取音高。",
  LOW_ENERGY_NO_F0: "声音电平太低，未绘制音高。",
  INSUFFICIENT_VOICED_FRAMES: "当前录音只提取到少量有效音高片段，暂时无法呈现完整语调走势。你仍可试听原音，并使用手动练习功能。",
  F0_EXTRACTION_FAILED: "音高提取失败，本次不提供音高判断。",
};

/** Explain existing frame evidence; no new acoustic threshold or admission rule. */
export function pitchEvidenceNote(track: Track): string {
  const count = track.frames.filter(frame => frame.voiced).length;
  if (track.status !== "AVAILABLE") return reasons[track.reason ?? ""] ?? "音高当前不可用，仍可试听与手动练习。";
  return `有效音高片段：${count} / ${track.frames.length} 帧。${track.observations?.late_minus_early_semitones == null ? "现有片段不足以比较首尾走势；保留实际点位，可继续试听与手动练习。" : "只展示实际可用片段，空白不直接表示停顿或发音错误。"}`;
}
