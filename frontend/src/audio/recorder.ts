import { encodeWav, parseWav } from "./wav";

// Development diagnostics contain metadata/counts only, never PCM samples.
function diagnostic(event: string, detail: unknown = {}) {
  if (import.meta.env.DEV)
    console.debug(`[Speech X-Ray Mic] ${event}`, JSON.stringify(detail));
}
function exception(error: unknown) {
  return error instanceof Error
    ? { name: error.name, message: error.message }
    : { name: "UnknownError", message: String(error) };
}
export type StereoDiagnostic = { leftRms: number; rightRms: number; mixedRms: number; stereoFrames: number; suspectedCancellation: boolean };
export type InputLevel = { rms: number; peak: number; suspectedCancellation: boolean };
export type RecordingProvenance = {
  source: "browser_microphone";
  processingSampleRate: number;
  observedInputChannels: number[];
  monoConversion: "none" | "arithmetic_mean_stereo";
  stereoDiagnostic?: StereoDiagnostic;
};
export class PcmRecorder {
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private source?: MediaStreamAudioSourceNode;
  private chunks: Float32Array[] = [];
  private cancelled = false;
  private stopping = false;
  private frames = 0;
  private reportedSecond = -1;
  private settle?: () => void;
  private rejectCapture?: (error: Error) => void;
  private initTimer?: ReturnType<typeof setTimeout>;
  private ended?: () => void;
  private processingRate = 0;
  private inputChannels = new Set<number>();
  private stereoDiagnostic?: StereoDiagnostic;
  private warnedCancellation = false;
  getProvenance(): RecordingProvenance {
    return {
      source: "browser_microphone",
      processingSampleRate: this.processingRate,
      observedInputChannels: [...this.inputChannels],
      monoConversion: this.inputChannels.has(2)
        ? "arithmetic_mean_stereo"
        : "none",
      ...(this.stereoDiagnostic ? { stereoDiagnostic: this.stereoDiagnostic } : {}),
    };
  }

  async start(
    onLimit: () => void,
    onError: (message: string) => void,
    onProgress: (seconds: number) => void = () => {},
    onInitializing: () => void = () => {},
    onLevel: (level: InputLevel) => void = () => {},
  ): Promise<boolean> {
    let granted = false;
    try {
      diagnostic("getUserMedia_request");
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
        video: false,
      });
      granted = true;
      diagnostic("getUserMedia_success");
      if (this.cancelled) {
        await this.dispose("late_permission_grant_after_cancel");
        return false;
      }
      const track = this.stream.getAudioTracks()[0];
      if (!track || track.readyState === "ended")
        throw new Error("媒体流中没有可用的音频轨道。");
      const settings = track.getSettings();
      diagnostic("track_metadata", {
        readyState: track.readyState,
        settings,
        constraints: track.getConstraints(),
      });
      onInitializing();
      // Metadata is a hint, not a validity gate. WAV uses the actual processing rate.
      const hint = settings.sampleRate;
      this.context = new AudioContext({
        sampleRate:
          Number.isInteger(hint) && hint! >= 8000 && hint! <= 48000
            ? hint
            : 48000,
      });
      const rate = this.context.sampleRate;
      this.processingRate = rate;
      diagnostic("audio_context", {
        sampleRate: rate,
        state: this.context.state,
        trackSampleRate: hint ?? "not provided",
        processingRateDiffersFromTrackMetadata: hint != null && hint !== rate,
        channelHandling:
          "mono unchanged; stereo arithmetic mean (L+R)/2; reject >2 channels",
      });
      if (!Number.isInteger(rate) || rate < 8000 || rate > 48000)
        throw new Error(`实际 PCM 处理采样率 ${rate} Hz 不在 8–48 kHz 范围。`);
      await this.context.audioWorklet.addModule(
        `${import.meta.env.BASE_URL}pcm-capture.js`,
      );
      if (this.cancelled) return false;
      diagnostic("worklet_initialized");
      this.node = new AudioWorkletNode(this.context, "pcm-capture", {
        channelCountMode: "max",
      });
      let firstFrame: () => void;
      const firstPcm = new Promise<void>((resolve, reject) => {
        firstFrame = resolve;
        this.rejectCapture = reject;
      });
      // Observe early setup failure/cancellation even before resume() is called.
      void firstPcm.catch(() => {});
      const captureError = (error: Error) => {
        if (this.cancelled || this.stopping) return;
        diagnostic("capture_exception", exception(error));
        if (this.rejectCapture) this.rejectCapture(error);
        else {
          void this.dispose("capture_error");
          onError(`录音中断：${error.message} 请检查输入设备或重新尝试。`);
        }
      };
      this.node.port.onmessage = (event) => {
        if (this.cancelled) return;
        const data = event.data;
        if (data.stereoDiagnostic) this.stereoDiagnostic = data.stereoDiagnostic;
        if (data.level) {
          onLevel(data.level);
          if (data.level.suspectedCancellation && !this.warnedCancellation) {
            this.warnedCancellation = true;
            diagnostic("stereo_cancellation_warning", this.stereoDiagnostic);
          }
        }
        if (data.inputChannels != null && !data.pcm)
          diagnostic("worklet_input", {
            inputChannelCount: data.inputChannels,
            processingSampleRate: data.processingSampleRate,
          });
        if (data.error) {
          captureError(new Error(data.error));
          return;
        }
        if (data.pcm instanceof Float32Array && data.pcm.length) {
          if (
            ![1, 2].includes(data.inputChannels) ||
            data.outputChannels !== 1 ||
            data.processingSampleRate !== rate
          ) {
            captureError(new Error("实际 PCM 声道或处理采样率不一致。"));
            return;
          }
          this.chunks.push(data.pcm);
          this.inputChannels.add(data.inputChannels);
          this.frames += data.pcm.length;
          if (this.rejectCapture) {
            clearTimeout(this.initTimer);
            this.rejectCapture = undefined;
            diagnostic("first_pcm_frames", {
              frameCount: data.pcm.length,
              sampleRate: rate,
              inputChannelCount: data.inputChannels,
              monoConversion: data.monoConversion,
            });
            firstFrame!();
          }
          const seconds = Math.floor(this.frames / rate);
          if (seconds !== this.reportedSecond) {
            this.reportedSecond = seconds;
            onProgress(seconds);
          }
        }
        if (data.stopped) { diagnostic("input_level_summary", this.stereoDiagnostic); this.settle?.(); }
        if (data.limit && !this.stopping) {
          diagnostic("stop_requested", {
            reason: "30_second_limit",
            frames: this.frames,
          });
          onLimit();
        }
      };
      this.node.onprocessorerror = () =>
        captureError(new Error("AudioWorklet 处理器异常。"));
      this.ended = () => captureError(new Error("麦克风音频轨道已结束。"));
      track.addEventListener("ended", this.ended);
      this.source = this.context.createMediaStreamSource(this.stream);
      this.source.connect(this.node);
      this.node.connect(this.context.destination);
      this.initTimer = setTimeout(
        () => captureError(new Error("初始化后 5 秒内未收到 PCM 帧。")),
        5000,
      );
      await Promise.all([this.context.resume(), firstPcm]);
      if (this.cancelled) return false;
      diagnostic("recording_started", this.getProvenance());
      return true;
    } catch (error) {
      diagnostic("initialization_exception", exception(error));
      const wasCancelled = this.cancelled;
      await this.dispose(
        wasCancelled ? "initialization_cancelled" : "initialization_failed",
      );
      if (wasCancelled) return false;
      if (error instanceof Error && error.name === "NotAllowedError")
        throw new Error(
          "麦克风权限未获允许。请在浏览器中允许此网站使用麦克风后重试。",
        );
      if (granted)
        throw new Error(
          "麦克风已授权，但录音初始化失败。请检查输入设备或重新尝试。",
        );
      throw new Error("无法访问麦克风。请检查输入设备、浏览器权限或重新尝试。");
    }
  }

  async stop(reason = "user_stop"): Promise<Blob> {
    diagnostic("stop_requested", { reason, frames: this.frames });
    if (this.stopping || this.cancelled) throw new Error("录音已经停止。");
    this.stopping = true;
    try {
      const rate = this.context?.sampleRate;
      if (!rate || !this.node || this.context?.state !== "running")
        throw new Error("录音处理器尚未就绪或已暂停，请重新录音。");
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error("录音处理器未确认停止，请重新录音。")),
          1000,
        );
        this.settle = () => {
          clearTimeout(timeout);
          resolve();
        };
        this.node!.port.postMessage("stop");
      });
      const samples = new Float32Array(this.frames);
      let at = 0;
      this.chunks.forEach((c) => {
        samples.set(c, at);
        at += c.length;
      });
      const buffer = encodeWav(samples, rate);
      const validated = parseWav(buffer);
      diagnostic("wav_validated", {
        channels: 1,
        format: "PCM16",
        sampleRate: validated.sampleRate,
        frames: validated.samples.length,
        durationMs: validated.durationMs,
        recordingProvenance: this.getProvenance(),
      });
      return new Blob([buffer], { type: "audio/wav" });
    } catch (error) {
      diagnostic("stop_exception", exception(error));
      throw error;
    } finally {
      await this.dispose(reason);
    }
  }

  async dispose(reason = "session_dispose") {
    this.cancelled = true;
    diagnostic("cleanup", {
      reason,
      frames: this.frames,
      contextState: this.context?.state,
    });
    clearTimeout(this.initTimer);
    this.rejectCapture?.(new Error("录音初始化已取消。"));
    this.rejectCapture = undefined;
    if (this.ended)
      this.stream
        ?.getAudioTracks()
        .forEach((t) => t.removeEventListener("ended", this.ended!));
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = undefined;
    this.source?.disconnect();
    this.source = undefined;
    this.node?.disconnect();
    if (this.node) {
      this.node.onprocessorerror = null;
      this.node.port.onmessage = null;
      this.node.port.close();
      this.node = undefined;
    }
    const context = this.context;
    this.context = undefined;
    if (context && context.state !== "closed") await context.close();
    this.chunks = [];
    diagnostic("cleanup_complete", { reason, contextState: context?.state, retainedPcmChunks: this.chunks.length, streamReleased: !this.stream, workletReleased: !this.node });
  }
}
