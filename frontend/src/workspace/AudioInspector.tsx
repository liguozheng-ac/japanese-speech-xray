import { useEffect, useMemo, useRef, useState } from "react";
import type { AudioAsset } from "../analysis/state";
import type { TimeSpan } from "../api/contract";
import { TARGETS, validSpan, PRACTICE } from "../analysis/mvp";
import { SegmentPlayer } from "../audio/playback";
import { emptySelection, selectionFrom, selectionStatus, updateSelection, timeAt } from "../audio/selection";
import type { AudioSelection, SelectionKind } from "../audio/selection";
import { ProsodyPanel } from "../prosody/ProsodyPanel";
import type { Curves } from "../prosody/curves";

export function AudioInspector({ audio, promptId, candidates, disabled, onChange, onRerecord, demoCurves }: {
  audio: AudioAsset; promptId?: string; candidates?: { word: TimeSpan | null; vowel: TimeSpan | null; reason: string };
  disabled: boolean; onChange: (selection: AudioSelection) => void; onRerecord?: () => void;
  demoCurves?: Curves;
}) {
  const selection = audio.selection ?? emptySelection;
  const [kind, setKind] = useState<SelectionKind>("word"), [error, setError] = useState(""), [playing, setPlaying] = useState("");
  const [view, setView] = useState({ start_ms: 0, end_ms: audio.durationMs });
  const [fields, setFields] = useState({ start: "", end: "" });
  const [showCandidate, setShowCandidate] = useState(false);
  const player = useRef<SegmentPlayer | null>(null), operation = useRef(0);
  const drag = useRef<{ anchor: number; mode: "new" | "start" | "end"; span: TimeSpan | null } | null>(null);
  const span = selection[kind], target = promptId ? TARGETS[promptId] : null;
  useEffect(() => { const p = new SegmentPlayer(); player.current = p; return () => { operation.current++; p.dispose(); player.current = null; }; }, [audio.blob]);
  useEffect(() => { if (disabled) { operation.current++; player.current?.stop(); } }, [disabled]);
  useEffect(() => { setFields({ start: span ? String(span.start_ms) : "", end: span ? String(span.end_ms) : "" }); }, [span?.start_ms, span?.end_ms, kind]);
  useEffect(() => { operation.current++; player.current?.stop(); setPlaying(""); setError(""); }, [kind, span?.start_ms, span?.end_ms]);
  const waveform = useMemo(() => {
    const started = performance.now(), count = 600;
    const first = Math.floor(view.start_ms * audio.sampleRate / 1000), last = Math.min(audio.samples.length, Math.ceil(view.end_ms * audio.sampleRate / 1000));
    const buckets = Array.from({ length: count }, (_, i) => {
      const a = first + Math.floor(i * (last - first) / count), b = first + Math.max(Math.floor((i + 1) * (last - first) / count), Math.floor(i * (last - first) / count) + 1);
      let lo = 0, hi = 0;
      for (let j = a; j < Math.min(last, b); j++) { lo = Math.min(lo, audio.samples[j]); hi = Math.max(hi, audio.samples[j]); }
      return [lo, hi];
    });
    const peak = Math.max(...buckets.flat().map(Math.abs)), gain = peak > 0 ? 1 / peak : 1;
    return { path: buckets.map(([lo, hi], i) => `M${i} ${48 - hi * gain * 40}V${48 - lo * gain * 40}`).join(""), milliseconds: performance.now() - started };
  }, [audio.samples, audio.sampleRate, view]);
  const x = (ms: number) => (ms - view.start_ms) / (view.end_ms - view.start_ms) * 600;
  const replace = (next: TimeSpan | null) => { setError(""); onChange(updateSelection(selection, kind, next)); };
  const audition = async (s: TimeSpan, label: string, loop = false) => {
    if (disabled || !validSpan(s, audio.durationMs)) { setError("试听区间无效，请检查起止时间。"); return; }
    const op = ++operation.current;
    setError(""); setPlaying("正在准备试听……");
    try {
      const ok = await player.current?.play(audio.blob, s.start_ms, s.end_ms, audio.durationMs, () => setPlaying(""), loop);
      if (ok && operation.current === op) setPlaying(`${loop ? "循环" : "正在"}试听${label} ${s.start_ms}–${s.end_ms} ms`);
    } catch (e) { if (operation.current === op) { setPlaying(""); setError(e instanceof Error ? e.message : "音频无法解码或试听。"); } }
  };
  // SegmentPlayer invalidates old decode results. UI token also prevents stale labels.
  const play = (s: TimeSpan, label: string, loop = false) => { player.current?.stop(); void audition(s, label, loop); };
  const locate = (event: React.PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const raw = view.start_ms + timeAt(event.clientX - bounds.left, bounds.width, view.end_ms - view.start_ms);
    return Math.min(audio.durationMs, Math.max(0, Math.round(raw * audio.sampleRate / 1000) * 1000 / audio.sampleRate));
  };
  const rounded = (ms: number) => Math.round(ms * 1000) / 1000;
  const manual = selection[kind], candidate = candidates?.[kind];
  return <section className="audio-inspector" aria-label="原音波形与区域选择" data-waveform-ms={waveform.milliseconds.toFixed(3)} data-ui-state="EVIDENCE_AVAILABLE">
    <div className="inspection-heading"><strong>01 · {demoCurves ? "演示音频" : "本次录音"}与语音波形</strong><span>{demoCurves ? "DEMO · Haruka 合成 WAV" : audio.recordingProvenance ? "本次浏览器录音" : "本次上传 WAV"} · {(audio.durationMs / 1000).toFixed(2)} s</span></div>
    {target && <p className="inspection-target" lang="ja">目标词 {target.word} · 长元音 {target.vowel}</p>}
    <div className="selection-tools" role="group" aria-label="区域类型">
      <button type="button" disabled={disabled} aria-pressed={kind === "word"} onClick={() => setKind("word")}>目标词区域</button>
      <button type="button" disabled={disabled} aria-pressed={kind === "vowel"} onClick={() => setKind("vowel")}>长元音练习区域</button>
    </div>
    <svg className={`selection-wave ${disabled ? "is-disabled" : ""}`} viewBox="0 0 600 96" preserveAspectRatio="none" role="img" aria-label="真实 WAV 波形；拖动框选，拖动选区两端调整；也可在下方输入毫秒" data-real-waveform="true"
      onPointerDown={event => {
        if (disabled || event.button !== 0) return;
        const at = locate(event), hit = (view.end_ms - view.start_ms) * 10 / event.currentTarget.getBoundingClientRect().width;
        drag.current = { anchor: at, span, mode: span && Math.abs(at - span.start_ms) <= hit ? "start" : span && Math.abs(at - span.end_ms) <= hit ? "end" : "new" };
        event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={event => {
        const d = drag.current; if (!d) return; const at = locate(event);
        try { const s = d.mode === "new" ? selectionFrom(d.anchor, at, audio.durationMs) : d.mode === "start" ? { start_ms: at, end_ms: d.span!.end_ms } : { start_ms: d.span!.start_ms, end_ms: at };
          if (validSpan(s, audio.durationMs)) replace({ start_ms: rounded(s.start_ms), end_ms: Math.min(audio.durationMs, rounded(s.end_ms)) });
        } catch { /* A click without a drag is not a region. */ }
      }} onPointerUp={event => { drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { drag.current = null; }}>
      <path d="M0 48H600" stroke="#d9dcdf"/><path d={waveform.path} stroke="#50545a" strokeWidth=".8"/>
      {showCandidate && candidate && validSpan(candidate, audio.durationMs) && <rect x={x(candidate.start_ms)} y="5" width={x(candidate.end_ms) - x(candidate.start_ms)} height="86" fill="none" stroke="#7b8189" strokeDasharray="4 4"/>}
      {manual && <g><rect x={x(manual.start_ms)} y="5" width={x(manual.end_ms) - x(manual.start_ms)} height="86" fill="#2670ff" fillOpacity=".10" stroke="#2670ff"/>
        <path d={`M${x(manual.start_ms)} 0V96M${x(manual.end_ms)} 0V96`} stroke="#2670ff" strokeWidth="2"/></g>}
    </svg>
    <div className="inspection-ticks">{Array.from({ length: 5 }, (_, i) => <span key={i}>{((view.start_ms + (view.end_ms - view.start_ms) * i / 4) / 1000).toFixed(2)} s</span>)}</div>
    <p className="sketch-note">原始 WAV 时间轴 · 蓝色为手动选择区域。拖动框选，或展开精确调整。</p>
    <div className="selection-actions practice-actions" role="group" aria-label="原音与选区试听">
      <button type="button" className="practice-button" disabled={disabled} onClick={() => play({ start_ms: 0, end_ms: audio.durationMs }, "原音")}>试听整段原音</button>
      <button type="button" className="practice-button" disabled={disabled || !span} onClick={() => span && play(span, "用户选区")}>试听选区</button>
      <button type="button" className="practice-button" disabled={disabled || !span} aria-pressed={playing.startsWith("循环")} onClick={() => span && play(span, "用户选区", true)}>循环试听选区</button>
      <button type="button" className="practice-button" disabled={!playing} onClick={() => { operation.current++; player.current?.stop(); setPlaying(""); }}>停止试听</button>
    </div>
    <details className="selection-secondary"><summary>精确调整 · 时间与缩放</summary>
    <div className="selection-tools">
      <button type="button" className="inline-action" disabled={!span} onClick={() => {
        if (!span) return; const padding = Math.max(100, (span.end_ms - span.start_ms) * .2);
        setView({ start_ms: Math.max(0, span.start_ms - padding), end_ms: Math.min(audio.durationMs, span.end_ms + padding) });
      }}>放大选区</button>
      <button type="button" className="inline-action" onClick={() => setView({ start_ms: 0, end_ms: audio.durationMs })}>查看整段</button>
      <button type="button" className="inline-action" disabled={disabled || !span} onClick={() => replace(null)}>清除当前选区</button>
    </div>
    <div className="selection-fields">
      <label>起点 (ms)<input type="number" step="1" min="0" max={audio.durationMs} value={fields.start} disabled={disabled} onChange={e => setFields({ ...fields, start: e.target.value })}/></label>
      <label>终点 (ms)<input type="number" step="1" min="0" max={audio.durationMs} value={fields.end} disabled={disabled} onChange={e => setFields({ ...fields, end: e.target.value })}/></label>
      <button type="button" className="practice-button" disabled={disabled} onClick={() => {
        const s = { start_ms: Number(fields.start), end_ms: Number(fields.end) };
        if (!fields.start || !fields.end || !validSpan(s, audio.durationMs)) setError("选区无效：需 0 ≤ 起点 < 终点 ≤ 原音时长。未更改选区。"); else replace(s);
      }}>应用时间</button>
    </div>
    </details>
    {span && <p className="selection-duration">用户{kind === "word" ? "词" : "长元音练习"}选区 {span.start_ms}–{span.end_ms} ms · 区间长度 {((span.end_ms - span.start_ms) / 1000).toFixed(3)} s（不代表已验证的长音真实时长）</p>}
    {selection.word && <button type="button" className="practice-button word-confirm" disabled={disabled || selection.wordConfirmed} onClick={() => onChange({ ...selection, wordConfirmed: true })}>试听后，我确认这是目标词范围</button>}
    {selection.wordConfirmed && <p className="trust-note" data-status="WORD_REGION_USER_CONFIRMED">已确认目标词所在区域。长元音的内部边界尚未经过可靠验证。</p>}
    {selection.vowel && <p className="trust-note" data-status="VOWEL_REGION_USER_SELECTED">长元音区域由你手动选择，仅用于练习试听，未经独立声学验证。</p>}
    <span hidden data-selection-status={selectionStatus(selection).join(" ")}/>
    {playing && <p role="status">{playing}</p>}
    {error && <p className="session-error" role="alert">{error}</p>}
    <ProsodyPanel audio={audio} promptId={promptId} disabled={disabled} demoCurves={demoCurves}/>
    <div className="practice-next"><strong>03 · 练习建议</strong><p>先听原音，找到想练习的片段，再对照同句合成参考。{PRACTICE}</p>
      {onRerecord && <button type="button" className="practice-button practice-primary" disabled={disabled} onClick={onRerecord}>{demoCurves ? "用这句重新练习" : "再次录音"}</button>}
    </div>
    {candidates && <details className="candidate-notice" onToggle={event => setShowCandidate(event.currentTarget.open)} data-ui-state={candidates.word ? "EXPERIMENTAL_BOUNDARY" : "USER_SELECTION_AVAILABLE"}>
      <summary>实验 X-Ray · 技术证据：模型候选边界</summary>
      <p>{candidates.word ? "已找到一段可能包含目标发音的语音。请先试听确认。自动边界仍处于实验验证阶段。" : "自动候选当前不可用，请手动选择。"}</p>
      {candidate ? <div className="selection-actions"><span>模型{kind === "word" ? "词" : "长元音"}候选 {candidate.start_ms}–{candidate.end_ms} ms</span>
        <button type="button" className="inline-action" disabled={disabled} onClick={() => play(candidate, "模型候选")}>试听候选</button>
        <button type="button" className="inline-action" disabled={disabled} onClick={() => replace(candidate)}>用候选作为选区起点</button></div> : <p className="sketch-note">{candidates.reason}。不补造边界。</p>}
    </details>}
  </section>;
}
