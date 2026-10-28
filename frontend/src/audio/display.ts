// Display only. Never changes PCM samples or the Blob submitted to the backend.
export function autoFitPeaks(peaks: readonly number[]): number[] {
  const peak = peaks.reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  return peak === 0 ? peaks.map(() => 0) : peaks.map(value => value / peak * 0.84);
}
