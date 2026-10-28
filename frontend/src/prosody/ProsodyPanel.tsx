import { useEffect, useRef, useState } from "react";
import type { AudioAsset } from "../analysis/state";
import { cachedCurves, extractCurves } from "./client";
import { pitchDomain, pitchEvidenceNote, reasons, segments, SEMITONE_METHOD } from "./curves";
import type { Curves, PitchUnit, Track } from "./curves";
import "./prosody.css";

function PitchPlot({ track, unit, domain, label, reference = false }: { track: Track; unit: PitchUnit; domain: [number, number]; label: string; reference?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const x = (time: number) => 44 + 590 * time / track.duration_ms;
  const y = (value: number) => 122 - 104 * (value - domain[0]) / (domain[1] - domain[0]);
  const frame = hover === null ? null : track.frames[Math.min(track.frames.length - 1, Math.round(hover / Number(track.parameters.hop_ms)))];
  return <div className={`pitch-track ${reference ? "pitch-reference" : ""}`}>
    <span className="pitch-track-label">{label}</span>
    {track.status === "AVAILABLE" && <p className="pitch-evidence-note">{pitchEvidenceNote(track)}</p>}
    {track.status === "AVAILABLE" ? <>
      <div className="pitch-chart-scroll"><svg viewBox="0 0 660 158" role="img" aria-label={`${label}真实音高曲线；无声和无可靠音高区域留空`} data-pitch-source={track.audio_sha256}
        onPointerMove={e => { const box = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(track.duration_ms, ((e.clientX - box.left) / box.width * 660 - 44) / 590 * track.duration_ms))); }} onPointerLeave={() => setHover(null)}>
        {[domain[0], (domain[0] + domain[1]) / 2, domain[1]].map(v => <g key={v}><path d={`M44 ${y(v)}H634`} stroke="#e7e8eb"/><text x="36" y={y(v) + 4} textAnchor="end">{Math.round(v)}</text></g>)}
        {segments(track, unit).map((s, i) => <g key={i} opacity={s.weak ? .35 : 1}>
          <path d={s.points.map((p, j) => `${j ? "L" : "M"}${x(p.time).toFixed(2)} ${y(p.value).toFixed(2)}`).join(" ")} fill="none" stroke="currentColor" strokeWidth="1.7" strokeDasharray={reference ? "4 2" : undefined}/>
          {s.points.length === 1 && <circle cx={x(s.points[0].time)} cy={y(s.points[0].value)} r="1.6" fill="currentColor"/>}
        </g>)}
        {hover !== null && <path d={`M${x(hover)} 14V126`} stroke="#aab0b8" strokeDasharray="2 3"/>}
        {[0, .25, .5, .75, 1].map(t => <text key={t} x={44 + 590 * t} y="149" textAnchor="middle">{(track.duration_ms / 1000 * t).toFixed(2)} s</text>)}
        <text x="4" y="10">{unit === "hz" ? "Hz" : "半音"}</text>
      </svg></div>
      <small className="pitch-mobile-hint">可横向滑动查看完整时间轴</small>
      <div className="pitch-readout" aria-live="off">{frame ? `${(frame.time_ms / 1000).toFixed(2)} s · ${frame.f0_hz === null ? "无可用音高" : `${frame.f0_hz.toFixed(1)} Hz`} · 有声概率 ${frame.voiced_probability === null ? "不可用" : frame.voiced_probability.toFixed(2)} · RMS ${frame.rms_dbfs.toFixed(1)} dBFS` : "移动指针查看帧证据 · 浅色段为较弱有声证据"}</div>
    </> : <p className="pitch-abstention" role="status">{reasons[track.reason ?? ""] ?? "音高当前不可用。"} 原音、波形与手动练习仍可使用。</p>}
  </div>;
}

export function ProsodyPanel({ audio, promptId, disabled, demoCurves }: { audio: AudioAsset; promptId?: string; disabled: boolean; demoCurves?: Curves }) {
  const [output, setOutput] = useState<{ blob: Blob; data: Curves } | null>(() => {
    const data = promptId ? cachedCurves(audio.blob, promptId) : null;
    return data ? { blob: audio.blob, data } : null;
  });
  // Suppress a previous sentence during the render before the reset effect runs.
  const result = demoCurves?.prompt_id === promptId ? demoCurves : output?.blob === audio.blob && output.data.prompt_id === promptId ? output.data : null;
  const [unit, setUnit] = useState<PitchUnit>("hz"), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), generation = useRef(0);
  useEffect(() => { generation.current++; request.current?.abort(); request.current = null; setBusy(false); setError(""); const data = promptId ? cachedCurves(audio.blob, promptId) : null; setOutput(data ? { blob: audio.blob, data } : null); return () => { generation.current++; request.current?.abort(); request.current = null; }; }, [audio.blob, promptId]);
  useEffect(() => { if (disabled) { generation.current++; request.current?.abort(); request.current = null; setBusy(false); } }, [disabled]);
  const load = async () => {
    if (!promptId || disabled || demoCurves || request.current) return;
    const id = ++generation.current, controller = new AbortController(); request.current = controller;
    setBusy(true); setError(""); setOutput(null);
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 45000);
    try {
      const value = await extractCurves(audio.blob, promptId, controller.signal);
      if (generation.current === id) setOutput({ blob: audio.blob, data: value });
    } catch (e) {
      if (generation.current === id && (!controller.signal.aborted || timedOut)) setError(timedOut ? "音高提取等待超时，请稍后重试。原音与手动练习仍可使用。" : e instanceof TypeError ? "无法连接本地音高服务。原音与手动练习仍可使用。" : e instanceof Error ? e.message : "音高提取失败。原音仍可使用。");
    } finally { clearTimeout(timeout); if (request.current === controller) request.current = null; if (generation.current === id) setBusy(false); }
  };
  const tracks = result ? [result.learner, ...(result.reference ? [result.reference] : [])] : [];
  const observations = result?.learner.observations;
  return <section className="prosody-panel" aria-label="音高与语调" data-prosody-state={busy ? "EXTRACTING" : result?.learner.status ?? "NOT_REQUESTED"}>
    <div className="pitch-heading"><strong>02 · 音高与语调</strong>{demoCurves ? <span className="pitch-note">已保存的 pYIN 提取结果</span> : <button type="button" className="practice-button" disabled={disabled || busy || !promptId} onClick={() => void load()}>{busy ? "正在提取真实音高……" : result ? "重新提取音高" : "查看音高与同句参考"}</button>}</div>
    {!result && <p className="pitch-note">从本次 WAV 提取音高，无需等待自动对齐。点击后仅发送到本地服务。</p>}
    {!promptId && <p className="pitch-note">先选择本次朗读的练习句。</p>}
    {busy && <p role="status" className="pitch-note">正在处理实际音频帧；原音与手动选区可继续使用。</p>}
    {error && <p className="session-error" role="alert">{error}</p>}
    {result && <>
      <div className="pitch-units" role="group" aria-label="音高显示单位"><button type="button" aria-pressed={unit === "hz"} onClick={() => setUnit("hz")}>真实频率 Hz</button><button type="button" aria-pressed={unit === "semitones"} onClick={() => setUnit("semitones")}>相对半音</button></div>
      <PitchPlot track={result.learner} unit={unit} domain={pitchDomain(tracks, unit)} label={demoCurves ? "DEMO · Haruka 合成 WAV" : audio.recordingProvenance ? "本次录音" : "本次 WAV"}/>
      {result.reference && <PitchPlot track={result.reference} unit={unit} domain={pitchDomain(tracks, unit)} label="同句 Haruka 合成参考" reference/>}
      <p className="pitch-reference-note">Haruka 合成参考 · 非母语者准确性标准。两条曲线使用各自原音时间轴，未进行音素对齐或时间拉伸。</p>
      {!result.reference && <p className="pitch-note" role="status">同句合成参考暂不可用；保留本次音高观察。</p>}
      {unit === "semitones" && <p className="pitch-note">{SEMITONE_METHOD}。各自中位数作为 0 半音，便于观察升降；不表示正确或合格。</p>}
      {observations && <p className="pitch-observations">本次有声帧音高范围（P10–P90） {observations.p10_f0_hz.toFixed(0)}–{observations.p90_f0_hz.toFixed(0)} Hz{observations.late_minus_early_semitones !== null && ` · 后 1/3 相对前 1/3 有声帧中位数 ${observations.late_minus_early_semitones >= 0 ? "+" : ""}${observations.late_minus_early_semitones.toFixed(1)} 半音`}</p>}
      <details className="pitch-details"><summary>方法与证据说明 · 音高与参考来源</summary>
        <p>参考对应所选练习句。请确认本次录音朗读相同文本；此模块不核验实际朗读内容。</p>
        <p>librosa 1.0.0 / pYIN · 范围 50–600 Hz · 原采样率 {result.learner.sample_rate_hz} Hz · 每 {String(result.learner.parameters.hop_ms)} ms 一帧 · 窗长 {String(result.learner.parameters.frame_length)} samples。未重采样，未插补无声音高。</p>
        <p>F0 是算法估计，仍可能出现倍频或半频错检。有声概率是 pYIN 模型证据，不是准确率。概率低于 0.10 或 RMS ≤ −60 dBFS 时留空；0.10–0.50 的有声帧浅色显示。这些是工程显示阈值，未经真人准确性校准。RMS 表示数字电平，不是声压级。清辅音、停顿、低电平和提取失败都会留空，空白不能直接判为停顿或发音错误。</p>
        <p>耗时：本次音高提取 {(result.learner.extraction_ms / 1000).toFixed(2)} s · 请求处理 {(result.total_ms / 1000).toFixed(2)} s。</p>
        {result.reference_source && <><p>参考：{result.reference_source.voice} · {result.reference_source.engine}</p><p lang="ja">同句原文：{result.reference_source.text}</p><p className="pitch-hash">参考 SHA-256：{result.reference_source.sha256}</p></>}
        <p>此模块不提供东京式重音判断、个人正确率或综合评分，也不改变长音参考统计。</p>
      </details>
    </>}
  </section>;
}
