// Shared by reference playback, user playback, capture, submit and reset.
// Never passes reference audio to the input/analysis path.
let stopSegment: (() => void) | undefined;
export function pauseOtherAudio(current?: HTMLAudioElement, resetReferences = false) {
  stopSegment?.();
  document.querySelectorAll<HTMLAudioElement>("audio").forEach(audio => {
    if (audio === current) return;
    audio.pause();
    if (resetReferences && audio.dataset.referenceReading === "true") audio.currentTime = 0;
  });
}

// Source offset/duration are scheduled by the audio clock, not timeupdate or a
// 16ms animation timer. This matters for 30–50ms targets. No new WAV is produced.
export class SegmentPlayer {
  private context: AudioContext | null = null;
  private source: AudioBufferSourceNode | null = null;
  private generation = 0;
  private disposed = false;
  private onStop: (() => void) | undefined;
  constructor(private factory: () => AudioContext = () => new AudioContext()) {}
  stop = () => {
    this.generation++;
    if (this.source) { this.source.onended = null; this.source.stop(); this.source.disconnect(); this.source = null; }
    if (stopSegment === this.stop) stopSegment = undefined;
    this.onStop?.(); this.onStop = undefined;
  };
  async play(blob: Blob, startMs: number, endMs: number, durationMs: number, onStop: () => void, loop = false) {
    if (this.disposed || ![startMs, endMs, durationMs].every(Number.isFinite) || startMs < 0 || endMs <= startMs || endMs > durationMs)
      throw new Error("试听区间无效或超出原始音频。");
    pauseOtherAudio(); this.stop();
    const token = ++this.generation;
    this.onStop = onStop; stopSegment = this.stop;
    const context = this.context ??= this.factory();
    try {
      await context.resume();
      const buffer = await context.decodeAudioData(await blob.arrayBuffer());
      if (token !== this.generation || this.disposed) return false;
      if (Math.abs(buffer.duration * 1000 - durationMs) > 1) throw new Error("解码后的播放时长与原始 WAV 不一致。");
      const source = context.createBufferSource(); this.source = source;
      source.buffer = buffer; source.connect(context.destination);
      source.loop = loop;
      if (loop) { source.loopStart = startMs / 1000; source.loopEnd = endMs / 1000; }
      source.onended = () => this.stop();
      if (loop) source.start(0, startMs / 1000);
      else source.start(0, startMs / 1000, (endMs - startMs) / 1000);
      return true;
    } catch (error) { if (token === this.generation) this.stop(); throw error; }
  }
  dispose() { this.disposed = true; this.stop(); void this.context?.close(); this.context = null; }
}
