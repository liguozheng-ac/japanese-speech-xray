// Preserve mono; explicitly average stereo (L+R)/2. Emit silence to speakers.
// This processing applies only to browser capture, never uploaded WAV files.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = true;
    this.frames = 0;
    this.lastChannels = -1;
    this.energy = { left: 0, right: 0, mixed: 0, stereoFrames: 0 };
    this.meterFrames = 0;
    this.meterEnergy = 0;
    this.meterPeak = 0;
    this.port.onmessage = (event) => {
      if (event.data === "stop") {
        this.active = false;
        this.port.postMessage({ stopped: true, stereoDiagnostic: this.stereoDiagnostic() });
      }
    };
  }
  stereoDiagnostic() {
    const n = this.energy.stereoFrames;
    const leftRms = n ? Math.sqrt(this.energy.left / n) : 0;
    const rightRms = n ? Math.sqrt(this.energy.right / n) : 0;
    const mixedRms = n ? Math.sqrt(this.energy.mixed / n) : 0;
    return { leftRms, rightRms, mixedRms, stereoFrames: n,
      // Strong device-monitoring signal only; no pronunciation judgement.
      suspectedCancellation: n >= sampleRate * 0.5 && Math.min(leftRms, rightRms) > 0.005 && mixedRms < Math.min(leftRms, rightRms) * 0.1 };
  }
  process(inputs) {
    if (!this.active) return false;
    const channels = inputs[0];
    if (channels?.length !== this.lastChannels) {
      this.lastChannels = channels?.length ?? 0;
      this.port.postMessage({
        inputChannels: this.lastChannels,
        processingSampleRate: sampleRate,
      });
    }
    if (!channels?.length) return true;
    if (
      channels.length > 2 ||
      (channels.length === 2 && channels[0].length !== channels[1].length)
    ) {
      this.active = false;
      this.port.postMessage({
        error: "录音设备提供了不支持的声道布局；只支持实际单声道或双声道。",
      });
      return false;
    }
    const pcm = channels[0].slice();
    if (channels.length === 2) {
      for (let i = 0; i < pcm.length; i++) {
        pcm[i] = (channels[0][i] + channels[1][i]) / 2;
        this.energy.left += channels[0][i] ** 2;
        this.energy.right += channels[1][i] ** 2;
        this.energy.mixed += pcm[i] ** 2;
      }
      this.energy.stereoFrames += pcm.length;
    }
    if (this.frames + pcm.length > sampleRate * 30) {
      this.active = false;
      this.port.postMessage({ limit: true });
      return false;
    }
    this.frames += pcm.length;
    for (const value of pcm) { this.meterEnergy += value * value; this.meterPeak = Math.max(this.meterPeak, Math.abs(value)); }
    this.meterFrames += pcm.length;
    if (this.meterFrames >= sampleRate / 10) {
      this.port.postMessage({ level: { rms: Math.sqrt(this.meterEnergy / this.meterFrames), peak: this.meterPeak,
        suspectedCancellation: this.stereoDiagnostic().suspectedCancellation }, stereoDiagnostic: this.stereoDiagnostic() });
      this.meterFrames = 0; this.meterEnergy = 0; this.meterPeak = 0;
    }
    this.port.postMessage(
      {
        pcm,
        inputChannels: channels.length,
        outputChannels: 1,
        processingSampleRate: sampleRate,
        monoConversion:
          channels.length === 2 ? "arithmetic_mean_stereo" : "none",
      },
      [pcm.buffer],
    );
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
