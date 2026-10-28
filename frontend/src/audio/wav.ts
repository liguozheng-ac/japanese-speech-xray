export const WAV_REQUIREMENT =
  "此音频不符合分析要求。请上传 Mono PCM16 WAV（8–48 kHz）。";
export type WavAudio = {
  samples: Float32Array;
  sampleRate: number;
  durationMs: number;
};
export function parseWav(buffer: ArrayBuffer): WavAudio {
  const v = new DataView(buffer);
  const reject = (): never => {
    throw new Error(WAV_REQUIREMENT);
  };
  const tag = (at: number) =>
    String.fromCharCode(...new Uint8Array(buffer, at, 4));
  if (buffer.byteLength < 44 || buffer.byteLength > 10 * 1024 * 1024) reject();
  if (
    tag(0) !== "RIFF" ||
    tag(8) !== "WAVE" ||
    v.getUint32(4, true) + 8 !== buffer.byteLength
  )
    reject();
  let fmt: number | null = null,
    data: number | null = null,
    size = 0;
  for (let at = 12; at + 8 <= buffer.byteLength; ) {
    const n = v.getUint32(at + 4, true);
    const start = at + 8;
    if (start + n > buffer.byteLength) reject();
    if (tag(at) === "fmt ") {
      if (fmt !== null || n < 16) reject();
      fmt = start;
    }
    if (tag(at) === "data") {
      if (data !== null) reject();
      data = start;
      size = n;
    }
    at = start + n + (n % 2);
  }
  if (fmt === null || data === null || size === 0 || size % 2) reject();
  const f = fmt!,
    d = data!,
    rate = v.getUint32(f + 4, true);
  if (
    v.getUint16(f, true) !== 1 ||
    v.getUint16(f + 2, true) !== 1 ||
    v.getUint16(f + 14, true) !== 16 ||
    rate < 8000 ||
    rate > 48000 ||
    v.getUint16(f + 12, true) !== 2 ||
    v.getUint32(f + 8, true) !== rate * 2
  )
    reject();
  const durationMs = (size / 2 / rate) * 1000;
  if (durationMs > 30000)
    throw new Error("音频超过后端 30 秒上限，请重新录制或选择较短的 WAV。");
  const samples = new Float32Array(size / 2);
  for (let i = 0; i < samples.length; i++)
    samples[i] = v.getInt16(d + i * 2, true) / 32768;
  return { samples, sampleRate: rate, durationMs };
}
export function encodeWav(samples: Float32Array, rate: number): ArrayBuffer {
  if (
    !samples.length ||
    !Number.isInteger(rate) ||
    rate < 8000 ||
    rate > 48000 ||
    samples.length > rate * 30
  )
    throw new Error("录音长度或采样率不符合要求。");
  const b = new ArrayBuffer(44 + samples.length * 2),
    v = new DataView(b);
  const write = (at: number, s: string) =>
    [...s].forEach((c, i) => v.setUint8(at + i, c.charCodeAt(0)));
  write(0, "RIFF");
  v.setUint32(4, b.byteLength - 8, true);
  write(8, "WAVE");
  write(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  write(36, "data");
  v.setUint32(40, samples.length * 2, true);
  samples.forEach((x, i) => {
    if (!Number.isFinite(x)) throw new Error("录音包含无效采样。");
    const s = Math.max(-1, Math.min(1, x));
    v.setInt16(44 + i * 2, Math.round(s * (s < 0 ? 32768 : 32767)), true);
  });
  return b;
}
export function waveformPeaks(samples: Float32Array, count = 600): number[] {
  return Array.from({ length: count }, (_, i) => {
    let peak = 0;
    const a = Math.floor((i * samples.length) / count),
      b = Math.floor(((i + 1) * samples.length) / count);
    for (let j = a; j < b; j++) peak = Math.max(peak, Math.abs(samples[j]));
    return peak;
  });
}
