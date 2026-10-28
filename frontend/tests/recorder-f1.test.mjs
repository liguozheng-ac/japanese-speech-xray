import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
const read = (p) => fs.readFileSync(new URL(p, import.meta.url), "utf8");
const transpile = (s) =>
  ts.transpileModule(s, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  }).outputText;
const importCode = (code) =>
  import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const wav = await importCode(transpile(read("../src/audio/wav.ts")));
const recorderCode = transpile(read("../src/audio/recorder.ts"))
  .replace(
    /import\s+\{[^}]+\}\s+from\s+["']\.\/wav["'];?/,
    () =>
      `const WAV_REQUIREMENT=${JSON.stringify(wav.WAV_REQUIREMENT)};const encodeWav=${wav.encodeWav.toString()};const parseWav=${wav.parseWav.toString()};`,
  )
  .replaceAll("import.meta.env.BASE_URL", "'/'")
  .replaceAll("import.meta.env.DEV", "true");
const { PcmRecorder } = await importCode(recorderCode);
const workletCode = read("../public/pcm-capture.js");

// Real recorder + shipped worklet under controlled device/resource doubles.
// These tests are not evidence of Windows/Chrome physical microphone acceptance.
function device({
  settings = {},
  rate = 48000,
  channels = 1,
  deny,
  pending = false,
  noFrames = false,
  moduleError = false,
  resumeError = false,
  contextRate = rate,
  noStopAck = false,
} = {}) {
  const proof = {
    stopped: 0,
    closed: 0,
    portsClosed: 0,
    disconnected: 0,
    logs: [],
    nodes: [],
    contexts: [],
    progress: [],
    errors: [],
  };
  const oldDebug = console.debug;
  console.debug = (event, detail) =>
    proof.logs.push([event, JSON.parse(detail)]);
  proof.restore = () => {
    console.debug = oldDebug;
  };
  const track = {
    readyState: "live",
    getSettings: () => settings,
    getConstraints: () => ({
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    }),
    addEventListener: (_, fn) => {
      proof.ended = fn;
    },
    removeEventListener: () => {
      proof.ended = undefined;
    },
    stop: () => {
      proof.stopped++;
      track.readyState = "ended";
    },
  };
  const stream = { getAudioTracks: () => [track], getTracks: () => [track] };
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async (constraints) => {
          assert.deepEqual(constraints.audio, {
            channelCount: 1,
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          });
          if (deny)
            throw new DOMException("Permission denied", "NotAllowedError");
          if (pending)
            return new Promise((resolve) => {
              proof.grant = () => resolve(stream);
            });
          // Each successful device request represents a fresh live track.
          track.readyState = "live";
          return stream;
        },
      },
    },
  });
  globalThis.AudioContext = class {
    state = "suspended";
    sampleRate = contextRate;
    destination = {};
    audioWorklet = {
      addModule: async () => {
        if (moduleError) throw new Error("worklet module failed");
      },
    };
    constructor(options) {
      proof.contexts.push({
        requestedRate: options.sampleRate,
        actualRate: this.sampleRate,
      });
    }
    createMediaStreamSource() {
      return {
        connect() {},
        disconnect() {
          proof.disconnected++;
        },
      };
    }
    async resume() {
      if (resumeError) throw new Error("resume failed");
      this.state = "running";
      if (!noFrames) queueMicrotask(() => proof.emit(128));
    }
    async close() {
      proof.closed++;
      this.state = "closed";
    }
  };
  globalThis.AudioWorkletNode = class {
    port = {
      postMessage: (data) => {
        if (!noStopAck) this.processor.port.onmessage({ data });
      },
      close: () => {
        proof.portsClosed++;
      },
    };
    constructor() {
      const node = this;
      let Processor;
      class Base {
        port = { postMessage: (data) => node.port.onmessage?.({ data }) };
      }
      const scope = vm.createContext({
        AudioWorkletProcessor: Base,
        sampleRate: contextRate,
        registerProcessor: (_, ctor) => {
          Processor = ctor;
        },
      });
      vm.runInContext(workletCode, scope);
      this.processor = new Processor();
      proof.nodes.push(this);
      proof.emit = (count, actualChannels = channels) =>
        this.processor.process([
          Array.from({ length: actualChannels }, () =>
            new Float32Array(count).fill(0.2),
          ),
        ]);
    }
    connect() {}
    disconnect() {
      proof.disconnected++;
    }
  };
  proof.start = (r) =>
    r.start(
      () => {
        proof.limit = true;
      },
      (e) => proof.errors.push(e),
      (s) => proof.progress.push(s),
      () => {
        proof.initializing = true;
      },
    );
  return proof;
}

test("missing metadata: grant -> actual PCM -> >=3s -> valid WAV -> cleanup", async () => {
  const p = device(),
    r = new PcmRecorder();
  try {
    assert.equal(await p.start(r), true);
    assert.equal(p.initializing, true);
    assert.equal(p.stopped, 0);
    p.emit(48000 * 3 - 128);
    assert.equal(p.progress.at(-1), 3);
    const blob = await r.stop(),
      audio = wav.parseWav(await blob.arrayBuffer());
    assert.equal(audio.sampleRate, 48000);
    assert.equal(audio.durationMs, 3000);
    assert.equal(audio.samples.length, 144000);
    assert.ok(Math.abs(audio.samples[0] - 0.2) < 1 / 32768);
    assert.equal(p.stopped, 1);
    assert.equal(p.closed, 1);
    assert.equal(p.portsClosed, 1);
    assert.equal(p.disconnected, 2);
    assert.ok(p.logs.some(([e]) => e.includes("wav_validated")));
    assert.ok(
      p.logs.every(([, data]) => !JSON.stringify(data).includes('"pcm"')),
    );
    await r.dispose("repeat_cleanup");
    assert.equal(p.stopped, 1);
    assert.equal(p.closed, 1);
  } finally {
    p.restore();
  }
});
test("metadata rate mismatch/stereo metadata does not override actual mono PCM", async () => {
  const p = device({ settings: { channelCount: 2, sampleRate: 44100 } }),
    r = new PcmRecorder();
  try {
    assert.equal(await p.start(r), true);
    assert.equal(p.contexts[0].requestedRate, 44100);
    const audio = wav.parseWav(await (await r.stop()).arrayBuffer());
    assert.equal(audio.sampleRate, 48000);
    assert.ok(
      p.logs.some(([, d]) => d.processingRateDiffersFromTrackMetadata === true),
    );
  } finally {
    p.restore();
  }
});
test("permission denied gives explicit Chinese error and concrete diagnostic", async () => {
  const p = device({ deny: true });
  try {
    await assert.rejects(p.start(new PcmRecorder()), /权限未获允许/);
    assert.equal(p.contexts.length, 0);
    assert.ok(
      p.logs.some(
        ([, d]) =>
          d.name === "NotAllowedError" && d.message === "Permission denied",
      ),
    );
  } finally {
    p.restore();
  }
});
test("actual stereo capture retains explicit session provenance with valid mono WAV", async () => {
  const p = device({
      channels: 2,
      settings: { channelCount: 2, sampleRate: 48000 },
    }),
    r = new PcmRecorder();
  try {
    await p.start(r);
    p.emit(48000 * 3 - 128);
    const audio = wav.parseWav(await (await r.stop()).arrayBuffer());
    assert.equal(audio.durationMs, 3000);
    assert.equal(audio.sampleRate, 48000);
    const { stereoDiagnostic, ...provenance } = r.getProvenance();
    assert.equal(stereoDiagnostic.suspectedCancellation, false);
    assert.ok(Math.abs(stereoDiagnostic.leftRms - stereoDiagnostic.mixedRms) < 1e-8);
    assert.deepEqual(provenance, {
      source: "browser_microphone",
      processingSampleRate: 48000,
      observedInputChannels: [2],
      monoConversion: "arithmetic_mean_stereo",
    });
    assert.ok(
      p.logs.some(
        ([e, d]) =>
          e.includes("wav_validated") &&
          d.recordingProvenance.monoConversion === "arithmetic_mean_stereo",
      ),
    );
  } finally {
    p.restore();
  }
});
test("cancel after two seconds discards PCM without encoding WAV and releases every resource", async () => {
  const p = device(), r = new PcmRecorder();
  try {
    await p.start(r); p.emit(48000 * 2 - 128);
    await r.dispose("user_cancel_recording");
    assert.equal(p.stopped, 1); assert.equal(p.closed, 1); assert.equal(p.portsClosed, 1);
    assert.equal(p.disconnected, 2); assert.deepEqual(r.chunks, []);
    assert.ok(!p.logs.some(([event]) => event.includes("wav_validated")));
    await assert.rejects(r.stop(), /已经停止/);
  } finally { p.restore(); }
});
test("cancel pending permission, then late grant stops stream without starting", async () => {
  const p = device({ pending: true }),
    r = new PcmRecorder();
  try {
    const start = p.start(r);
    await r.dispose("permission_wait_cancelled");
    p.grant();
    assert.equal(await start, false);
    assert.equal(p.stopped, 1);
    assert.equal(p.contexts.length, 0);
  } finally {
    p.restore();
  }
});
test("no actual PCM cannot enter RECORDING; initialization cancel releases resources", async () => {
  const p = device({ noFrames: true }),
    r = new PcmRecorder();
  try {
    let resolved = false;
    const start = p.start(r).then((v) => {
      resolved = true;
      return v;
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(resolved, false);
    assert.equal(p.initializing, true);
    await r.dispose("initialization_cancelled");
    assert.equal(await start, false);
    assert.equal(p.stopped, 1);
    assert.equal(p.closed, 1);
  } finally {
    p.restore();
  }
});
test("no PCM initialization times out with explicit error and cleanup", async () => {
  const p = device({ noFrames: true });
  try {
    await assert.rejects(
      p.start(new PcmRecorder()),
      /麦克风已授权，但录音初始化失败/,
    );
    assert.ok(p.logs.some(([, d]) => d.message?.includes("5 秒内未收到 PCM")));
    assert.equal(p.closed, 1);
    assert.equal(p.stopped, 1);
  } finally {
    p.restore();
  }
});
for (const options of [
  { moduleError: true },
  { resumeError: true },
  { contextRate: 96000 },
])
  test(`initialization exception is visible and cleaned: ${JSON.stringify(options)}`, async () => {
    const p = device(options);
    try {
      await assert.rejects(
        p.start(new PcmRecorder()),
        /麦克风已授权，但录音初始化失败/,
      );
      assert.equal(p.closed, 1);
      assert.equal(p.stopped, 1);
    } finally {
      p.restore();
    }
  });
test("actual >2-channel input rejected explicitly without unknown conversion", async () => {
  const p = device({ channels: 3 });
  try {
    await assert.rejects(
      p.start(new PcmRecorder()),
      /麦克风已授权，但录音初始化失败/,
    );
    assert.ok(p.logs.some(([, d]) => d.inputChannelCount === 3));
    assert.ok(p.logs.some(([, d]) => d.message?.includes("不支持的声道布局")));
    assert.equal(p.stopped, 1);
    assert.equal(p.closed, 1);
  } finally {
    p.restore();
  }
});
test("runtime processor error invokes error callback and disposes", async () => {
  const p = device(),
    r = new PcmRecorder();
  try {
    await p.start(r);
    p.nodes[0].onprocessorerror();
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(p.errors[0], /录音中断/);
    assert.equal(p.closed, 1);
    assert.equal(p.stopped, 1);
  } finally {
    p.restore();
  }
});
test("device ending after start reports interruption and cleanup", async () => {
  const p = device(),
    r = new PcmRecorder();
  try {
    await p.start(r);
    p.ended();
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(p.errors[0], /轨道已结束/);
    assert.equal(p.stopped, 1);
    assert.equal(p.closed, 1);
  } finally {
    p.restore();
  }
});
test("stop acknowledgement failure refuses partial output and cleans resources", async () => {
  const p = device({ noStopAck: true }),
    r = new PcmRecorder();
  try {
    await p.start(r);
    await assert.rejects(r.stop(), /未确认停止/);
    assert.equal(p.closed, 1);
    assert.equal(p.stopped, 1);
  } finally {
    p.restore();
  }
});
test("re-record uses fresh recorder and both sessions clean independently", async () => {
  const p = device();
  try {
    for (let i = 0; i < 2; i++) {
      const r = new PcmRecorder();
      await p.start(r);
      p.emit(48000 * 3 - 128);
      assert.equal(
        wav.parseWav(await (await r.stop()).arrayBuffer()).durationMs,
        3000,
      );
    }
    assert.equal(p.stopped, 2);
    assert.equal(p.closed, 2);
    assert.equal(p.portsClosed, 2);
  } finally {
    p.restore();
  }
});
