/** Authored engineering tone for structural UI tests; never speech or DEMO evidence. */
export function engineeringWav(durationMs = 3520, sampleRate = 16000) {
  const count = Math.round(durationMs * sampleRate / 1000);
  const bytes = new Uint8Array(44 + count * 2), v = new DataView(bytes.buffer);
  const tag = (at, text) => [...text].forEach((c, i) => v.setUint8(at + i, c.charCodeAt(0)));
  tag(0, 'RIFF'); v.setUint32(4, bytes.length - 8, true); tag(8, 'WAVE');
  tag(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  tag(36, 'data'); v.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) v.setInt16(44 + i * 2, Math.round(Math.sin(i * 2 * Math.PI * 220 / sampleRate) * 4000), true);
  return bytes;
}
