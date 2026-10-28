import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
const source = (path) =>
  fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
async function module(path) {
  let code = ts.transpileModule(source(path), {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  }).outputText;
  code = code
    .replace(
      /import\s+\{[^}]+\}\s+from\s+["']\.\/wav["'];?/,
      () =>
        `const WAV_REQUIREMENT=${JSON.stringify(wav.WAV_REQUIREMENT)}; const encodeWav=${encodeWav.toString()}; const parseWav=${parseWav.toString()};`,
    )
    .replace("import.meta.env.BASE_URL", "'/'")
    .replaceAll("import.meta.env.DEV", "false");
  return import(
    `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`
  );
}
const wav = await module("audio/wav.ts");
const { parseWav, encodeWav } = wav;
const {
  initialSession,
  sessionReducer: r,
  canSubmit,
} = await module("analysis/state.ts");
const { mapAnalysis, focusFor } = await module("analysis/mapper.ts");
const { validateContract } = await module("api/validate.ts");
const { ObjectUrls } = await module("audio/objectUrls.ts");
const fixture = JSON.parse(
  fs.readFileSync(
    new URL(
      "../../data/examples/api-v1-analysis-response.json",
      import.meta.url,
    ),
  ),
);
const schema = JSON.parse(
  fs.readFileSync(
    new URL(
      "../../data/contracts/api-v1-analysis.schema.json",
      import.meta.url,
    ),
  ),
);
const valid = () =>
  encodeWav(
    Float32Array.from({ length: 16000 }, (_, i) => Math.sin(i / 12) * 0.5),
    16000,
  );
const asset = {
  ...parseWav(valid()),
  blob: new Blob([valid()]),
  url: "blob:test",
  name: "test.wav",
};
const prompt = fixture.prompt;
const ready = () =>
  r(r(initialSession, { type: "PROMPT", prompt }), {
    type: "AUDIO",
    audio: asset,
  });
test("PCM16 encoding/decoding preserves sample count, rate and quantized amplitude", () => {
  const a = parseWav(valid());
  assert.equal(a.samples.length, 16000);
  assert.equal(a.sampleRate, 16000);
  assert.equal(a.durationMs, 1000);
  assert.ok(Math.abs(a.samples[10] - Math.sin(10 / 12) * 0.5) < 1 / 32768);
});
for (const [label, at, value, width] of [
  ["stereo", 22, 2, 2],
  ["8-bit", 34, 8, 2],
  ["float codec", 20, 3, 2],
  ["rate below limit", 24, 7999, 4],
  ["rate above limit", 24, 48001, 4],
  ["wrong block alignment", 32, 4, 2],
  ["wrong byte rate", 28, 12345, 4],
])
  test(`reject ${label}`, () => {
    const b = valid(),
      v = new DataView(b);
    width === 2 ? v.setUint16(at, value, true) : v.setUint32(at, value, true);
    assert.throws(() => parseWav(b));
  });
test("reject MP3 even with WAV filename", () =>
  assert.throws(() =>
    parseWav(new TextEncoder().encode("ID3" + "x".repeat(100)).buffer),
  ));
test("reject truncated and inconsistent RIFF length", () => {
  assert.throws(() => parseWav(valid().slice(0, 50)));
  const b = valid();
  new DataView(b).setUint32(40, 999999, true);
  assert.throws(() => parseWav(b));
});
test("reject empty PCM and invalid float samples", () => {
  assert.throws(() => encodeWav(new Float32Array(), 16000));
  assert.throws(() => encodeWav(new Float32Array([NaN]), 16000));
});
test("valid 8k and 48k boundaries and bounded recording", () => {
  for (const rate of [8000, 48000])
    assert.equal(
      parseWav(encodeWav(new Float32Array(rate), rate)).sampleRate,
      rate,
    );
  assert.throws(() => encodeWav(new Float32Array(8000 * 30 + 1), 8000));
});
test("submit requires both prompt/audio and AUDIO_READY", () => {
  assert.equal(canSubmit(initialSession), false);
  assert.equal(canSubmit(r(initialSession, { type: "PROMPT", prompt })), false);
  assert.equal(
    canSubmit(r(initialSession, { type: "AUDIO", audio: asset })),
    false,
  );
  assert.equal(canSubmit(ready()), true);
  for (const phase of ["RECORDING", "ANALYZING", "ERROR", "VALIDATING_AUDIO"])
    assert.equal(canSubmit({ ...ready(), phase }), false);
});
test("single inflight request blocks reset while composer remains available", () => {
  const s = r(r(ready(), { type: "START" }), { type: "REQUEST_STARTED", id: 1, at: 100 });
  assert.equal(r(s, { type: "RESET" }), s);
  assert.equal(r(s, { type: "START" }), s);
  assert.equal(r(s, { type: "PHASE", phase: "REQUESTING_MIC" }).phase, "REQUESTING_MIC");
  assert.equal(r(s, { type: "PROMPT", prompt }).prompt, prompt);
  assert.equal(s.turns.length, 1);
});
test("permission waiting is separate from actual recording, with late-capture guard", () => {
  let s = r(ready(), { type: "PHASE", phase: "REQUESTING_MIC" });
  assert.equal(canSubmit(s), false);
  assert.equal(r(s, { type: "PROMPT", prompt }), s);
  s = r(s, { type: "CAPTURE_STARTED" });
  assert.equal(s.phase, "RECORDING");
  assert.equal(r(initialSession, { type: "CAPTURE_STARTED" }), initialSession);
});
test("completion replaces waiting turn in place and expands it", () => {
  const s = r(r(r(ready(), { type: "START" }), { type: "REQUEST_STARTED", id: 1, at: 100 }), {
    type: "RESULT",
    id: 1, at: 200,
    response: fixture,
  });
  assert.equal(s.turns.length, 1);
  assert.equal(s.expanded, 1);
  assert.equal(s.turns[0].audio, asset);
  assert.equal(s.composerOpen, true);
});
test("second turn preserves first result and accordion is exclusive", () => {
  let s = r(r(r(ready(), { type: "START" }), { type: "REQUEST_STARTED", id: 1, at: 100 }), {
    type: "RESULT",
    id: 1, at: 200,
    response: fixture,
  });
  s = r(s, { type: "CONTINUE" });
  assert.equal(s.turns.length, 1);
  s = r(r(s, { type: "PROMPT", prompt }), { type: "AUDIO", audio: asset });
  s = r(s, { type: "START" });
  assert.equal(s.turns.length, 2);
  s = r(r(s, { type: "REQUEST_STARTED", id: 2, at: 300 }), { type: "RESULT", id: 2, at: 400, response: fixture });
  assert.equal(s.expanded, 2);
  s = r(s, { type: "EXPAND", id: 1 });
  assert.equal(s.expanded, 1);
  s = r(s, { type: "EXPAND", id: 1 });
  assert.equal(s.expanded, null);
  assert.equal(r(s, { type: "RESET" }), initialSession);
});
test("operational errors stay in current Turn and preserve prior Turn", () => {
  let s = r(r(r(ready(), { type: "START" }), { type: "REQUEST_STARTED", id: 1, at: 100 }), {
    type: "RESULT",
    id: 1, at: 200,
    response: fixture,
  });
  s = r(s, { type: "CONTINUE" });
  s = r(r(s, { type: "PROMPT", prompt }), { type: "AUDIO", audio: asset });
  s = r(r(r(s, { type: "START" }), { type: "REQUEST_STARTED", id: 2, at: 300 }), { type: "TURN_ERROR", id: 2, at: 400, message: "SERVICE_BUSY" });
  assert.equal(s.turns.length, 2);
  assert.equal(s.turns[0].response, fixture);
  assert.equal(s.turns[1].error, "SERVICE_BUSY");
});
test("schema validates fixture; missing target or wrong unit type is rejected", () => {
  validateContract(fixture, schema, schema.$defs);
  const broken = structuredClone(fixture);
  broken.audio.duration_ms = "1 second";
  assert.throws(() => validateContract(broken, schema, schema.$defs));
  broken.audio.duration_ms = NaN;
  assert.throws(() => validateContract(broken, schema, schema.$defs));
});
test("mapper preserves genuine spans and unavailable evidence", () => {
  const f = structuredClone(fixture);
  const m = mapAnalysis(f);
  assert.equal(m.timeline, f.timeline);
  const absent = structuredClone(f);
  absent.targets[0].duration = null;
  absent.targets[0].availability.duration = false;
  assert.match(mapAnalysis(absent).targets[0].duration, /不可用/);
});
test("mora focus never invents a midpoint or individual boundary", () => {
  const f = structuredClone(fixture);
  const a = f.timeline.morae[0];
  a.shared_span = null;
  assert.equal(focusFor(mapAnalysis(f), "mora", a.index).span, null);
  const shared = f.timeline.morae.find((m) => m.shared_span);
  if (shared)
    assert.deepEqual(
      focusFor(mapAnalysis(f), "mora", shared.index).span,
      shared.shared_span,
    );
});
test("partial and abstained status are availability labels", () => {
  for (const status of ["PARTIAL_EVIDENCE", "ABSTAINED"]) {
    const f = structuredClone(fixture);
    f.status = status;
    assert.doesNotMatch(mapAnalysis(f).status, /正确|错误|好|坏|分数/);
  }
});
test("worklet preserves mono, explicitly averages stereo and stops at limit", () => {
  let Processor;
  class Base {
    port = { postMessage: (m) => this.messages.push(m) };
    messages = [];
  }
  const ctx = vm.createContext({
    AudioWorkletProcessor: Base,
    sampleRate: 8000,
    registerProcessor: (_, c) => (Processor = c),
  });
  vm.runInContext(
    fs.readFileSync(
      new URL("../public/pcm-capture.js", import.meta.url),
      "utf8",
    ),
    ctx,
  );
  const p = new Processor(),
    pcm = new Float32Array([0.25, -0.3]);
  assert.equal(p.process([[pcm]]), true);
  assert.deepEqual([...p.messages.find((m) => m.pcm).pcm], [...pcm]);
  p.port.onmessage({ data: "stop" });
  assert.equal(p.messages.at(-1).stopped, true);
  assert.equal(p.process([[pcm]]), false);
  const stereo = new Processor();
  const right = new Float32Array([-0.25, 0.1]);
  assert.equal(stereo.process([[pcm, right]]), true);
  const mixed = stereo.messages.find((m) => m.pcm);
  assert.equal(mixed.inputChannels, 2);
  assert.equal(mixed.monoConversion, "arithmetic_mean_stereo");
  assert.equal(mixed.pcm[0], 0);
  assert.ok(Math.abs(mixed.pcm[1] - -0.1) < 1e-7);
  const multichannel = new Processor();
  assert.equal(multichannel.process([[pcm, pcm, pcm]]), false);
  assert.ok(multichannel.messages.find((m) => m.error).error);
  const limit = new Processor();
  limit.frames = 8000 * 30;
  assert.equal(limit.process([[pcm]]), false);
  assert.equal(limit.messages.find((m) => m.limit).limit, true);
});
test("late permission grant after disposal stops new stream", async () => {
  let grant,
    stopped = 0;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: () => new Promise((resolve) => (grant = resolve)),
      },
    },
  });
  const { PcmRecorder } = await module("audio/recorder.ts");
  const r = new PcmRecorder(),
    pending = r.start(
      () => {},
      () => {},
    );
  await r.dispose();
  grant({ getTracks: () => [{ stop: () => stopped++ }] });
  await pending;
  assert.equal(stopped, 1);
});
test("object URL replacement releases only draft, then session clear releases all Turns", async () => {
  const pool = new ObjectUrls(),
    first = pool.create(new Blob(["first turn"])),
    draft = pool.create(new Blob(["draft"]));
  pool.release(draft);
  await assert.rejects(fetch(draft));
  assert.equal(await (await fetch(first)).text(), "first turn");
  const second = pool.create(new Blob(["second turn"]));
  pool.clear();
  await assert.rejects(fetch(first));
  await assert.rejects(fetch(second));
  pool.clear();
});
