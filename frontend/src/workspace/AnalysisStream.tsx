import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AudioAsset, Turn } from "../analysis/state";
import {
  focusFor,
  mapAnalysis,
  number,
  overlaps,
  seconds,
  warningText,
} from "../analysis/mapper";
import type { AnalysisViewModel, Focus } from "../analysis/mapper";
import type { Target, TimeSpan } from "../api/contract";
import { waveformPeaks } from "../audio/wav";
import { autoFitPeaks } from "../audio/display";
import type { Prompt } from "../api/contract";
import { ReferenceReading } from "./ReferenceReading";
import { elapsedLabel } from "./elapsed";
import { SegmentPlayer } from "../audio/playback";
import { STAGES } from "../api/progress";
import { AudioInspector } from "./AudioInspector";
import type { AudioSelection } from "../audio/selection";
import { candidatesFor, turnEvidenceState, UNAVAILABLE, TARGETS } from "../analysis/mvp";
import type { Curves } from "../prosody/curves";

function Waveform({
  audio,
  element,
  span,
  playhead,
}: {
  audio: AudioAsset;
  element: HTMLAudioElement | null;
  span: TimeSpan | null;
  playhead: number;
}) {
  const peaks = useMemo(() => autoFitPeaks(waveformPeaks(audio.samples)), [audio.samples]);
  const scale = (ms: number) =>
    Math.max(0, Math.min(600, (ms / audio.durationMs) * 600));
  const path = peaks
    .map((p, i) => `M${i} ${42 - p * 40}V${42 + p * 40}`)
    .join("");
  return (
    <div className="waveform-track">
      <svg viewBox="0 0 600 84" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 42H600" stroke="#d3d5d8" />
        <path d={path} stroke="#424548" strokeWidth=".65" />
        {span && (
          <>
            <rect
              x={scale(span.start_ms)}
              y="4"
              width={scale(span.end_ms) - scale(span.start_ms)}
              height="76"
              fill="#2670ff"
              fillOpacity=".10"
            />
            <path
              d={path}
              stroke="#2670ff"
              strokeWidth=".8"
              style={{
                clipPath: `inset(0 ${(600 - scale(span.end_ms)) / 6}% 0 ${scale(span.start_ms) / 6}%)`,
              }}
            />
          </>
        )}
        <path
          d={`M${scale(playhead * 1000)} 0V84`}
          stroke="#111"
          strokeWidth="1"
        />
      </svg>
      <input
        type="range"
        min="0"
        max={audio.durationMs / 1000}
        step="0.01"
        value={Math.min(playhead, audio.durationMs / 1000)}
        aria-label="定位音频播放位置"
        onChange={(e) => {
          if (element) element.currentTime = Number(e.target.value);
        }}
      />
      <div className="waveform-ticks">
        <span>0 s</span>
        <span>{seconds(audio.durationMs)}</span>
      </div>
    </div>
  );
}

function XRay({
  vm,
  audio,
  element,
  playhead,
  focus,
  onFocus,
}: {
  vm: AnalysisViewModel;
  audio: AudioAsset;
  element: HTMLAudioElement | null;
  playhead: number;
  focus: Focus | null;
  onFocus: (focus: Focus | null) => void;
}) {
  const [full, setFull] = useState(false);
  const timeline = vm.timeline;
  if (!timeline)
    return (
      <p className="unavailable">
        当前结构证据不可用。{vm.warnings.map((w) => warningText(w.reason_code)).join(" ")}
      </p>
    );
  const target = vm.targets[0]?.target,
    selectedWord = focus?.wordIndex ?? target?.word_index;
  const focused = (
    kind: Focus["kind"],
    index: number,
    word: number | null,
    span: TimeSpan | null,
  ) => {
    if (!focus) return false;
    if (focus.kind === kind && focus.index === index) return true;
    if (focus.kind === "word") return word === focus.wordIndex;
    if (kind === "word") return index === focus.wordIndex;
    return !!span && !!focus.span && overlaps(span, focus.span);
  };
  const select = (kind: Focus["kind"], index: number) =>
    onFocus(focusFor(vm, kind, index));
  return (
    <section className="xray-structure" aria-label="声音结构 X-Ray">
      <div className="xray-heading">
        <span>{target?.surface ?? "声音结构"}</span>
        <span aria-hidden="true">
          │<br />↓
        </span>
      </div>
      <div className="xray-row">
        <span className="sketch-label">Waveform</span>
        <Waveform
          audio={audio}
          element={element}
          span={focus ? focus.span : (target?.time_span ?? null)}
          playhead={playhead}
        />
      </div>
      <div className="xray-row">
        <span className="sketch-label">Word</span>
        <div className="xray-entities" lang="ja">
          {timeline.words.map((w) => (
            <button
              type="button"
              key={w.index}
              aria-label={`词：${w.surface}`}
              aria-pressed={focused("word", w.index, w.index, w)}
              onClick={() => select("word", w.index)}
            >
              {w.surface}
            </button>
          ))}
        </div>
      </div>
      <div
        className={`xray-guide ${focus ? "has-focus" : ""}`}
        aria-hidden="true"
      >
        │
      </div>
      <div className="xray-row">
        <span className="sketch-label">Mora</span>
        <div className="xray-entities" lang="ja">
          {timeline.morae
            .filter((m) => full || m.word_index === selectedWord)
            .map((m) => (
              <button
                type="button"
                key={m.index}
                aria-label={`音拍：${m.representation} ${m.index}`}
                aria-pressed={focused(
                  "mora",
                  m.index,
                  m.word_index,
                  m.shared_span,
                )}
                onClick={() => select("mora", m.index)}
              >
                {m.representation}
              </button>
            ))}
        </div>
      </div>
      <div
        className={`xray-guide ${focus?.span ? "has-focus" : ""}`}
        aria-hidden="true"
      >
        │
      </div>
      <div className="xray-row">
        <span className="sketch-label">Phone · 原生标签</span>
        <div className="xray-entities phone-entities">
          {timeline.phones
            .filter((p) => full || p.word_index === selectedWord)
            .map((p) => (
              <button
                type="button"
                key={p.index}
                aria-label={`音素：${p.symbol} ${p.index}`}
                aria-pressed={focused("phone", p.index, p.word_index, p)}
                onClick={() => select("phone", p.index)}
              >
                {p.symbol}
              </button>
            ))}
        </div>
      </div>
      <p className="sketch-note" role="status">
        {focus?.kind === "mora" && !focus.span
          ? "该音拍没有独立声学边界，未创建波形时间区间。"
          : "长元音可由两个音拍共用一个原始音素区间；未拆分时间边界。"}
      </p>
      <p className="sketch-note">Phone 保留模型原生符号，未替换为目标音或补造 IPA。冻结目标：{TARGETS[vm.source.prompt.prompt_id]?.vowel ?? "不可用"}。符号体系及目标匹配可能存在歧义，不能据此判定读音正确。</p>
      <button
        type="button"
        className="inline-action"
        aria-expanded={full}
        onClick={() => setFull(!full)}
      >
        {full ? "收起完整结构" : "查看完整结构"}
      </button>
    </section>
  );
}

function ReferenceSketch({
  target,
  linked,
  demo = false,
}: {
  target: Target;
  linked: boolean;
  demo?: boolean;
}) {
  const [focus, setFocus] = useState<"candidate" | "median" | null>(null);
  const audioLabel = demo ? "演示音频" : "你的语音";
  const r = target.availability.reference ? target.reference : null,
    d = target.availability.duration ? target.duration : null;
  if (!r) return <p className="unavailable">母语者参考：当前证据不可用。</p>;
  const candidate = d?.rate_normalized_duration;
  const lo = Math.min(r.minimum, candidate ?? r.minimum),
    hi = Math.max(r.maximum, candidate ?? r.maximum),
    range = hi - lo || 1;
  const x = (value: number) => 40 + ((value - lo) / range) * 480;
  return (
    <section className="reference-sketch" aria-label="母语者参考摘要">
      <div className="xray-row">
        <span className="sketch-label">Reference</span>
        <div>
          <svg
            viewBox="0 0 560 116"
            role="img"
            aria-label="母语者参考观测范围、四分位线段、中位数和本次归一化时长；没有直方图样本"
          >
            <path
              d={`M${x(r.minimum)} 52H${x(r.maximum)} M${x(r.minimum)} 45V59 M${x(r.maximum)} 45V59`}
              stroke="#7a7d82"
              fill="none"
            />
            <path
              d={`M${x(r.q25)} 52H${x(r.q75)}`}
              stroke="#202326"
              strokeWidth="5"
            />
            <path
              d={`M${x(r.median)} 40V73`}
              stroke={focus === "median" ? "#2670ff" : "#222"}
              strokeWidth="1.5"
            />
            <text
              x={x(r.median)}
              y="92"
              textAnchor="middle"
              fontSize="12"
              fill={focus === "median" ? "#2670ff" : "#555"}
            >
              {number(r.median)}
            </text>
            {candidate != null && (
              <>
                <text
                  x={x(candidate)}
                  y="14"
                  textAnchor={x(candidate) > 400 ? "end" : x(candidate) < 160 ? "start" : "middle"}
                  fontSize="12"
                  fill={focus === "candidate" || linked ? "#2670ff" : "#222"}
                >
                  {audioLabel}（无单位） · {number(candidate)}
                </text>
                <path
                  d={`M${x(candidate)} 21V37m-4-5 4 5 4-5`}
                  stroke={focus === "candidate" || linked ? "#2670ff" : "#222"}
                  fill="none"
                />
              </>
            )}
          </svg>
          <div className="reference-actions">
            <button
              type="button"
              aria-label={audioLabel}
              aria-pressed={focus === "candidate"}
              disabled={candidate == null}
              onClick={() => setFocus("candidate")}
            >
              {audioLabel} <span>{number(candidate)} · 无单位</span>
            </button>
            <button
              type="button"
              aria-label="参考中位数"
              aria-pressed={focus === "median"}
              onClick={() => setFocus("median")}
            >
              参考中位数 <span>{number(r.median)} · 无单位</span>
            </button>
          </div>
          <p className="sketch-note">
            语速归一化值（无单位）。线段表示参考统计摘要，未绘制虚构频数。
          </p>
          <details className="reference-help">
            <summary>参考值说明</summary>
            <p>什么是参考中位数？系统先根据整句话的语速对目标长音时长进行归一化，再与参考说话者的同类特征比较。</p>
            <p>参考中位数表示参考分布的中间位置，不是秒数、分数或标准答案。低于或高于中位数只表示相对位置，不直接代表发音正确或错误。</p>
          </details>
          {focus === "median" && (
            <p className="reference-provenance">
              {r.independent_speaker_count} 位独立说话者的母语者参考 ·{" "}
              句子语境等价性未经验证；参考不规定本次发音应该有多长。
            </p>
          )}
          {focus === "candidate" && (
            <p className="reference-provenance">
              本次语速归一化值 {number(candidate)}（无单位）。
              {target.deviation
                ? {
                    BELOW_REFERENCE_MEDIAN: "低于参考中位数",
                    AT_REFERENCE_MEDIAN: "位于参考中位数",
                    ABOVE_REFERENCE_MEDIAN: "高于参考中位数",
                  }[target.deviation.direction]
                : "参考位置证据不可用"}
              。
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function Evidence({ vm, audition, playbackDisabled, demo = false }: { vm: AnalysisViewModel; audition: (span: TimeSpan | null, label: string) => void; playbackDisabled: boolean; demo?: boolean }) {
  const [showJson, setShowJson] = useState(false);
  return (
    <section className="evidence-notes" aria-label="证据摘要">
      {vm.targets.map(({ target: t, duration, direction, realization }) => (
        <div key={t.target_id}>
          <dl>
            <dt>目标词 / 冻结目标音</dt>
            <dd lang="ja">{t.surface} · {TARGETS[vm.source.prompt.prompt_id]?.vowel ?? "目标定义不可用"}</dd>
            <dt>候选区间原生标签</dt>
            <dd>{vm.timeline?.phones.filter(p => t.time_span && p.start_ms === t.time_span.start_ms && p.end_ms === t.time_span.end_ms && p.word_index === t.word_index).map(p => p.symbol).join(" ") || "候选标签不可用"} · 模型原生输出，符号与目标匹配尚未验证</dd>
            <dt>模型候选区间时长</dt>
            <dd>{duration}</dd>
            <dt>试听实际选区</dt>
            <dd className="target-audition">
              <button type="button" className="inline-action" disabled={!t.time_span || playbackDisabled} onClick={() => audition(t.time_span, "模型长元音候选")}>▶ 试听模型长元音候选</button>
              {t.time_span && <span>{t.time_span.start_ms}–{t.time_span.end_ms} ms（{vm.provenance.alignment_engine === "NARABAS_CPU_WORKER" ? "两个原生 phone 的包络" : "原始 phone 区间"}）</span>}
              {vm.timeline?.words.filter(w => w.index === t.word_index).map(w => <span key={w.index}><button type="button" className="inline-action" disabled={playbackDisabled} onClick={() => audition(w, "目标词")}>▶ 试听目标词</button> {w.start_ms}–{w.end_ms} ms</span>)}
            </dd>
            <dt>语速归一化值</dt>
            <dd>{demo ? "演示音频" : "你的语音"} {t.availability.duration ? number(t.duration?.rate_normalized_duration) : "不可用"} · 参考中位数 {t.availability.reference ? number(t.reference?.median) : "不可用"}（无单位）</dd>
            <dt>参考位置</dt>
            <dd>{direction}</dd>
            <dt>实现证据</dt>
            <dd>{realization}</dd>
          </dl>
          {t.reasons.map((r, i) => (
            <p className="unavailable" key={i}>
              参考说明：{warningText(r.reason_code)}
            </p>
          ))}
          <details>
            <summary>查看证据</summary>
            <dl>
              {Object.entries(t.availability).map(([key, value]) => (
                <div className="dl-row" key={key}>
                  <dt>
                    {
                      (
                        {
                          duration: "时长",
                          reference: "母语者参考",
                          deviation: "相对位置",
                          realization: "实验实现探针",
                          raw_f0: "原始 F0",
                          rms: "RMS",
                        } as Record<string, string>
                      )[key]
                    }
                  </dt>
                  <dd>{value ? "证据可用" : "当前证据不可用"}</dd>
                </div>
              ))}
              <dt>语速归一化值（无单位）</dt>
              <dd>
                {t.availability.duration
                  ? number(t.duration?.rate_normalized_duration)
                  : "当前证据不可用"}
              </dd>
              <dt>探针候选</dt>
              <dd>
                {t.realization
                  ? `${t.realization.canonical_pronunciation.join(" ")} / ${t.realization.experimental_reduced_pronunciation?.join(" ") ?? "不可用"}。实验工程证据。`
                  : "当前证据不可用"}
              </dd>
              <dt>原始 F0</dt>
              <dd>
                {t.availability.raw_f0
                  ? `${number(t.acoustics?.raw_f0_median_hz)} Hz（原始声学测量）`
                  : "当前证据不可用"}
              </dd>
              <dt>RMS</dt>
              <dd>
                {t.availability.rms
                  ? number(t.acoustics?.rms_median)
                  : "当前证据不可用"}
              </dd>
            </dl>
          </details>
          <p className="trust-note">上述数据依赖未经独立验证的自动边界。候选区间时长不等于已验证的长音真实时长；参考统计不是合格范围。本 MVP 不据此生成个人发音诊断。</p>
        </div>
      ))}
      {vm.warnings.map((w, i) => (
        <p key={i} className="unavailable">
          参考说明：{warningText(w.reason_code)}
        </p>
      ))}
      <details className="technical-details">
        <summary>技术细节</summary>
        <p>语速归一化值 = 长音原始时长 × 句子音拍数 ÷ 核心语音时长（无单位）。参考中位数不是秒数、分数或标准答案。</p>
        <p>波形已自动缩放以便观察，不代表绝对响度。{vm.provenance.alignment_engine === "NARABAS_CPU_WORKER"
          ? "长音区间取两个原生元音 phone 的起止包络；两个音拍共享该区间，原生边界未被扩长或切分。"
          : "长音区间时长来自原始长元音 phone；两个音拍共享同一个区间，没有人为切分。"}</p>
        <button type="button" className="inline-action" onClick={() => {
          const url = URL.createObjectURL(new Blob([JSON.stringify(vm.source, null, 2)], { type: "application/json" }));
          const link = document.createElement("a"); link.href = url; link.download = `${vm.id}-response.json`; link.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}>导出本次分析 JSON（不含音频）</button>
        <button type="button" className="inline-action" aria-expanded={showJson} onClick={() => setShowJson(!showJson)}>{showJson ? "收起分析 JSON" : "查看分析 JSON（不含音频）"}</button>
        {showJson && <textarea className="analysis-json" readOnly rows={6} aria-label="本次分析 JSON（不含音频）" value={JSON.stringify(vm.source, null, 2)}/>}
        {[...vm.warnings, ...vm.targets.flatMap(t => t.target.reasons)].map((w,i) => <p key={i} className="unavailable">{w.message} · {w.reason_code}</p>)}
        <dl>
          <dt>Prompt ID</dt>
          <dd>{vm.source.prompt.prompt_id}</dd>
          <dt>Analysis ID</dt>
          <dd>{vm.id}</dd>
          <dt>Pipeline</dt>
          <dd>
            {vm.source.status} · {vm.provenance.pipeline_version}
          </dd>
          <dt>输入</dt>
          <dd>
            {vm.source.audio.sample_rate_hz} Hz · {vm.source.audio.channels}{" "}
            channel · PCM16 WAV · {seconds(vm.source.audio.duration_ms)}
          </dd>
          {vm.targets.map(({ target: t }) => (
            <div className="technical-target" key={t.target_id}>
              <dt>Reference</dt>
              <dd>
                {t.reference?.target_id ?? "不可用"} ·{" "}
                {t.reference?.version ?? "不可用"}
              </dd>
              <dt>Median / MAD</dt>
              <dd>
                {number(t.reference?.median)} / {number(t.reference?.mad)}
              </dd>
              <dt>参考四分位</dt>
              <dd>
                {number(t.reference?.q25)} – {number(t.reference?.q75)}；IQR{" "}
                {number(t.reference?.iqr)}
              </dd>
              <dt>观测范围</dt>
              <dd>
                {number(t.reference?.minimum)} – {number(t.reference?.maximum)}
              </dd>
              <dt>长音区间时长（秒）</dt>
              <dd>
                {t.duration ? seconds(t.duration.raw_duration_ms) : "不可用"}
              </dd>
              <dt>语速归一化值/每音拍（无单位）</dt>
              <dd>
                {number(t.duration?.rate_normalized_duration)} /{" "}
                {number(t.duration?.rate_normalized_duration_per_mora)}
              </dd>
              <dt>差值 / 比值 / MAD距离</dt>
              <dd>
                {number(t.deviation?.signed_delta)} /{" "}
                {number(t.deviation?.ratio_to_median)} /{" "}
                {number(t.deviation?.mad_distance)}
              </dd>
              <dt>参考摘要 hash</dt>
              <dd>{t.reference?.profile_sha256 ?? "不可用"}</dd>
            </div>
          ))}
          <dt>Alignment</dt>
          <dd>
            {vm.provenance.alignment_engine}{" "}
            {vm.provenance.alignment_engine_version}；
            {vm.timeline?.basis ?? "不可用"}
          </dd>
          {vm.provenance.alignment_provenance && <>
            <dt>音素序列 / 对齐采样率</dt>
            <dd>{vm.provenance.alignment_provenance.phone_sequence_version} · {vm.provenance.alignment_provenance.alignment_sample_rate_hz} Hz</dd>
            <dt>重采样方法</dt>
            <dd>{vm.provenance.alignment_provenance.resample_method}</dd>
          </>}
          <dt>比较角色</dt>
          <dd>{vm.provenance.comparison_role}</dd>
          <dt>语音在参考中</dt>
          <dd>{String(vm.provenance.candidate_audio_in_reference)}</dd>
          <dt>语境等价验证</dt>
          <dd>
            {String(vm.provenance.sentence_context_equivalence_validated)}
          </dd>
          <dt>跨条件 likelihood 可比</dt>
          <dd>{String(vm.provenance.cross_condition_likelihood_comparable)}</dd>
          <dt>已标注学习者 / 校准诊断就绪</dt>
          <dd>
            {String(vm.provenance.real_labelled_learner_data_ready)} /{" "}
            {String(vm.provenance.calibrated_diagnosis_ready)}
          </dd>
          <dt>运行时 identity</dt>
          <dd>{vm.provenance.runtime_identity_sha256}</dd>
        </dl>
      </details>
    </section>
  );
}

function AnalysisTurn({
  turn,
  expanded,
  onToggle,
  playbackDisabled,
  onRetry,
  onCancelQueued,
  onCancelTurn,
  onSelection,
  demoCurves,
}: {
  turn: Turn;
  expanded: boolean;
  onToggle: () => void;
  playbackDisabled: boolean;
  onRetry: (prompt: Prompt) => void;
  onCancelQueued: (id: number) => void;
  onCancelTurn: (id: number) => void;
  onSelection: (id: number, selection: AudioSelection) => void;
  demoCurves?: Curves;
}) {
  const audioRef = useRef<HTMLAudioElement>(null),
    [element, setElement] = useState<HTMLAudioElement | null>(null),
    [playhead, setPlayhead] = useState(0),
    [playing, setPlaying] = useState(false),
    [playError, setPlayError] = useState("");
  const [focus, setFocus] = useState<Focus | null>(null);
  const segment = useRef<SegmentPlayer | null>(null);
  const [segmentLabel, setSegmentLabel] = useState("");
  useEffect(() => { const player = new SegmentPlayer(); segment.current = player; return () => { player.dispose(); segment.current = null; }; }, []);
  useEffect(() => { if (playbackDisabled) segment.current?.stop(); }, [playbackDisabled]);
  const audition = (span: TimeSpan | null, label: string) => {
    if (!span || playbackDisabled) return;
    setPlayError("");
    const playback = segment.current?.play(turn.audio.blob, span.start_ms, span.end_ms, turn.audio.durationMs, () => setSegmentLabel(""));
    setSegmentLabel(`正在试听${label}：${span.start_ms}–${span.end_ms} ms`);
    void playback?.catch(() => { setSegmentLabel(""); setPlayError("浏览器未能试听此区间，请重新尝试。"); });
  };
  const bindAudio = useCallback((node: HTMLAudioElement | null) => {
    audioRef.current = node;
    setElement(node);
  }, []);
  const vm = useMemo(
    () => (turn.response ? mapAnalysis(turn.response) : null),
    [turn.response],
  );
  const candidates = useMemo(() => candidatesFor(turn.response, turn.prompt.prompt_id, turn.audio.durationMs), [turn.response, turn.prompt.prompt_id, turn.audio.durationMs]);
  return (
    <article
      id={`analysis-turn-${turn.id}`}
      className={`analysis-turn ${expanded ? "is-expanded" : ""}`}
      aria-label={`分析 ${turn.id}`}
      data-ui-state={turnEvidenceState(turn)}
    >
      <span className="turn-index">{String(turn.id).padStart(2, "0")}</span>
      <div className="turn-content">
        <header className="turn-header">
          <h2 lang="ja">{turn.prompt.display_text}</h2>
          <div className="turn-tools">
            <button
              type="button"
              className="audio-play"
              disabled={playbackDisabled}
              aria-label={
                playing
                  ? `暂停分析 ${turn.id} 音频`
                  : `播放分析 ${turn.id} 音频`
              }
              onClick={() => {
                const a = audioRef.current;
                if (a) {
                  if (a.paused)
                    void a
                      .play()
                      .catch(() => setPlayError("浏览器未能播放此音频。"));
                  else a.pause();
                }
              }}
            >
              {playing ? "Ⅱ" : "▶"}{" "}
              <span>{(turn.audio.durationMs / 1000).toFixed(2)} s</span>
            </button>
            <ReferenceReading promptId={turn.prompt.prompt_id} disabled={playbackDisabled} />
            {vm && (
              <button
                type="button"
                className="inline-action"
                aria-expanded={expanded}
                onClick={onToggle}
              >
                {expanded ? "收起练习详情 ↑" : "展开练习详情 ↓"}
              </button>
            )}
          </div>
        </header>
        <audio
          ref={bindAudio}
          src={turn.audio.url}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={() => setPlayError("原音无法解码或播放，请重新选择合法 WAV。")}
          onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
        />
        {playError && <p role="alert">{playError}</p>}
        {segmentLabel && <p role="status">{segmentLabel} <button type="button" className="inline-action" onClick={() => segment.current?.stop()}>停止试听</button></p>}
        {turn.status === "QUEUED" && <div className="analysis-wait" role="status"><p>等待分析</p><p>前一条分析完成后将自动开始</p><button className="inline-action" type="button" onClick={() => onCancelQueued(turn.id)}>取消排队</button></div>}
        {turn.status === "ANALYZING" && (
          <Analyzing turn={turn} onCancel={() => onCancelTurn(turn.id)} />
        )}
        {turn.status === "CANCELLED" && <div className="analysis-wait" role="status"><p>分析已取消</p><p>后台计算已停止，资源已释放。</p><button className="inline-action" type="button" disabled={playbackDisabled} onClick={() => onRetry(turn.prompt)}>重新录音 / 重新分析</button></div>}
        {turn.error && (
          <div className="session-error" role="alert">
            <p>分析未完成</p><p>{turn.error}</p>
            <button className="inline-action" type="button" disabled={playbackDisabled} onClick={() => onRetry(turn.prompt)}>重新录音 / 重新分析</button>
            <a className="inline-action" href={turn.audio.url} download={`speech-xray-${turn.id}-original.wav`}>下载原始 WAV</a>
          </div>
        )}
        {(!vm || expanded) && <AudioInspector audio={turn.audio} promptId={turn.prompt.prompt_id} candidates={turn.response ? candidates : undefined} onRerecord={() => onRetry(turn.prompt)}
          disabled={playbackDisabled} onChange={selection => onSelection(turn.id, selection)} demoCurves={demoCurves}/>}
        {vm && (
          <>
            {vm.targets.some(t => t.target.reasons.some(r => r.reason_code === "ALIGNMENT_UNUSABLE")) && <div className="analysis-wait" role="status"><p>未能可靠对齐这段录音</p><p>录音已读取，但未能找到它与目标句子的有效对应，因此这次不提供时间结构、时长或发音判断。</p><p>请先试听录音，检查声音是否清晰、目标句子是否完整，以及是否有较长停顿。也可以下载原始 WAV，保留同一段音频用于排查。</p><a className="inline-action" href={turn.audio.url} download={`speech-xray-${turn.id}-original.wav`}>下载原始 WAV</a></div>}
            <p className="turn-summary">
              {candidates.word ? "实验性候选可用 · 请先试听确认；强制对齐成功不证明读对文本或边界准确。" : UNAVAILABLE}
            </p>
            {!expanded && <button className="inline-action" type="button" disabled={playbackDisabled} onClick={() => onRetry(turn.prompt)}>{demoCurves ? "用这句重新练习" : "再次录音练习"}</button>}
            {expanded && (
              <div className="expanded-xray">
                {candidates.structureAvailable ? <details className="experimental-details" open={demoCurves ? true : undefined}><summary>04 · 实验 X-Ray · 技术证据</summary>
                <p className="trust-note">实验 X-Ray 结构与研究数据（未经边界验证）</p>
                <p className="trust-note">模型预测的词、音拍和音素时间仅供观察。用户确认词区域不验证内部元音边界。历史 MFA 参考与新候选参考均不能作为个人合格标准；句子语境等价性尚未验证。</p>
                <XRay
                  vm={vm}
                  audio={turn.audio}
                  element={element}
                  playhead={playhead}
                  focus={focus}
                  onFocus={setFocus}
                />
                {vm.targets.map((t) => (
                  <ReferenceSketch
                    key={t.target.target_id}
                    target={t.target}
                    demo={!!demoCurves}
                    linked={
                      !!focus?.span &&
                      !!t.target.time_span &&
                      overlaps(focus.span, t.target.time_span)
                    }
                  />
                ))}
                <Evidence vm={vm} audition={audition} playbackDisabled={playbackDisabled} demo={!!demoCurves} />
                </details> : <p className="unavailable">{candidates.reason}。未展示不合法的自动结构或推断时长。</p>}
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}
function Analyzing({ turn, onCancel }: { turn: Turn; onCancel: () => void }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (turn.requestStartedAt == null) return;
    setNow(performance.now());
    const timer = window.setInterval(() => setNow(performance.now()), 1000);
    return () => window.clearInterval(timer);
  }, [turn.requestStartedAt]);
  return <div className="analysis-wait">
    <div role="status"><span className="wait-line" aria-hidden="true"/><p>{turn.cancelRequested ? "正在取消分析……" : "正在分析声音……"}</p><p>{turn.cancelRequested ? "正在停止后台计算并清理资源，请稍候。" : turn.requestStartedAt == null ? "正在提交音频……" : "已提交音频，正在等待分析结果"}</p></div>
    {turn.progress ? <section className="stage-progress" aria-label="分析阶段" data-request-key={turn.progress.request_key} data-request-id={turn.progress.request_id}>
      <p>分析阶段 {turn.progress.stage_index} / 5</p>
      <ol>{STAGES.map((label, i) => <li key={label}><span aria-hidden="true">{i + 1 === turn.progress!.stage_index ? "●" : turn.progress!.history.some(h => h.stage_index === i + 1) ? "✓" : "○"}</span> {label}</li>)}</ol>
      <p>阶段进度 {turn.progress.stage_index * 20}%</p>
      <p className="sketch-note">阶段进度表示当前分析步骤，不代表剩余时间比例。</p>
    </section> : <p>正在等待后端阶段信息……</p>}
    {turn.progressError && <p className="sketch-note" role="status">{turn.progressError}</p>}
    <p className="elapsed-time">已耗时 <time>{elapsedLabel(turn.requestStartedAt, now)}</time></p>
    <button type="button" className="inline-action" disabled={turn.cancelRequested} onClick={onCancel}>{turn.cancelRequested ? "正在取消……" : "取消分析"}</button>
    {turn.cancelError && <p role="alert">{turn.cancelError}</p>}
  </div>;
}
export function AnalysisStream({
  turns,
  expanded,
  onToggle,
  playbackDisabled,
  onRetry,
  onCancelQueued,
  onCancelTurn,
  onSelection,
  demoCurves,
}: {
  turns: Turn[];
  expanded: number | null;
  onToggle: (id: number) => void;
  playbackDisabled: boolean;
  onRetry: (prompt: Prompt) => void;
  onCancelQueued: (id: number) => void;
  onCancelTurn: (id: number) => void;
  onSelection: (id: number, selection: AudioSelection) => void;
  demoCurves?: Curves;
}) {
  const newest = turns.at(-1)?.id;
  const lastScrolled = useRef(0);
  useEffect(() => {
    // Only a new submission scrolls. Response/expansion/retry never moves the reader.
    if (newest && newest > lastScrolled.current) { document.getElementById(`analysis-turn-${newest}`)?.scrollIntoView({ block: "start", behavior: "instant" }); lastScrolled.current = newest; }
  }, [newest]);
  return (
    <section className="analysis-stream" aria-label="当前会话分析流">
      {turns.map((t) => (
        <AnalysisTurn
          key={t.id}
          turn={t}
          expanded={expanded === t.id}
          onToggle={() => onToggle(t.id)}
          playbackDisabled={playbackDisabled}
          onRetry={onRetry}
          onCancelQueued={onCancelQueued}
          onCancelTurn={onCancelTurn}
          onSelection={onSelection}
          demoCurves={demoCurves}
        />
      ))}
    </section>
  );
}
