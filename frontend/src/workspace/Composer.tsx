import { useRef, useState } from "react";
import { Arrow, Mic, Plus, WorkspaceIcon } from "../components/Icons";
import { canSubmit, locked, queuedCount } from "../analysis/state";
import type { useSession } from "./useSession";
import { ReferenceReading } from "./ReferenceReading";
import { AudioInspector } from "./AudioInspector";
import { TARGETS, inputEvidenceState } from "../analysis/mvp";
export function Composer({
  session,
}: {
  session: ReturnType<typeof useSession>;
}) {
  const { state, prompts, dispatch } = session,
    file = useRef<HTMLInputElement>(null);
  const lock = locked(state);
  const recording = ["REQUESTING_MIC", "RECORDING"].includes(state.phase);
  const [confirmedIdle, setConfirmedIdle] = useState(false);
  return (
    <section className="session-composer" aria-label="下一次分析输入" data-ui-state={inputEvidenceState(state.phase, !!state.audio)}>
      <div
        className="workspace-voice-entry"
        role="group"
        aria-label="上传、录音和提交分析"
      >
        <button
          className="workspace-add"
          type="button"
          disabled={lock}
          aria-label="上传 WAV"
          onClick={() => file.current?.click()}
        >
          <Plus />
        </button>
        <span className="workspace-placeholder">
          {state.phase === "REQUESTING_MIC"
            ? session.initializingMic
              ? "麦克风已授权，正在初始化录音……"
              : "正在等待麦克风权限……"
            : state.phase === "RECORDING"
              ? `正在录音 ${String(Math.floor(session.recordingSeconds / 60)).padStart(2, "0")}:${String(session.recordingSeconds % 60).padStart(2, "0")} · 点击停止`
              : state.audio
                ? "原音已就绪，可试听与练习"
                : state.prompt
                  ? "朗读下面的受控句子……"
                  : state.turns.length ? "继续分析一句日语……" : "说一句日语，开始分析……"}
        </span>
        <div className="voice-input-actions">
          <button
            className="voice-input-mic"
            type="button"
            disabled={state.phase === "VALIDATING_AUDIO"}
            aria-label={recording ? "停止录音" : "开始录音"}
            aria-pressed={recording}
            onClick={() => {
              void session.record();
            }}
          >
            {recording ? <span className="record-stop" /> : <Mic />}
          </button>
          <button
            className="voice-input-trigger"
            type="button"
            disabled={!canSubmit(state)}
            aria-label="开始分析 / Submit to X-Ray"
            title="可选实验 X-Ray：自动对齐可能需要数分钟，可取消；无需等待它进行基础练习"
            onClick={() => void session.submit()}
          >
            <Arrow />
          </button>
        </div>
      </div>
      <input
        ref={file}
        type="file"
        accept=".wav,audio/wav"
        hidden
        disabled={lock}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void session.upload(f);
          e.target.value = "";
        }}
      />
      {state.prompt && (
        <div className="prompt-reading">
        <p className="controlled-sentence" lang="ja">
          {state.prompt.display_text}
        </p>
        <ReferenceReading promptId={state.prompt.prompt_id} disabled={lock} />
        </div>
      )}
      {state.audio && (
        <div className="audio-confirm">
          <span>
            {state.audio.name} · {(state.audio.durationMs / 1000).toFixed(2)} s
            · {state.audio.sampleRate} Hz
          </span>
          <audio
            controls
            onPlay={e => { if (lock) e.currentTarget.pause(); }}
            preload="metadata"
            src={state.audio.url}
            aria-label="试听待分析音频"
          />
          <button
            type="button"
            disabled={lock}
            onClick={() => file.current?.click()}
          >
            替换 WAV
          </button>
        </div>
      )}
      {state.audio && <AudioInspector key={state.audio.url} audio={state.audio} promptId={state.prompt?.prompt_id} disabled={lock} onRerecord={() => { void session.record(); }}
        onChange={selection => dispatch({ type: "SELECTION", selection })}/>}
      {recording && <div className="recording-controls">
        <button type="button" className="inline-action" onClick={() => void session.cancelRecording()}>× 取消录制</button>
        <button type="button" className="inline-action" disabled={state.phase !== "RECORDING"} onClick={() => void session.stop()}>■ 完成录制</button>
        {state.phase === "RECORDING" && <span className="input-level">输入电平 <meter aria-label="录音输入电平（仅监视）" min="0" max="1" value={session.inputLevel?.peak ?? 0}/></span>}
      </div>}
      {state.phase === "RECORDING" && (
        <p className="composer-note" role="status">
          录音最长 30 秒；浏览器可能仍进行设备处理。尚未提交分析。
        </p>
      )}
      {state.error && state.composerOpen && (
        <p className="session-error" role="alert">
          {state.error}
        </p>
      )}
      {state.audio?.recordingProvenance?.monoConversion ===
        "arithmetic_mean_stereo" && (
        <p className="composer-note">
          本次设备提供双声道，录音已按 (L + R) / 2
          转为单声道；未降噪或归一化。浏览器仍可能进行设备处理。
        </p>
      )}
      {(session.inputLevel?.suspectedCancellation || state.audio?.recordingProvenance?.stereoDiagnostic?.suspectedCancellation) && <p className="composer-note" role="status">检测到双声道合并后电平明显降低。可尝试更换输入设备后重新录制。</p>}
      {queuedCount(state) >= 3 && <p className="composer-note" role="status">已有 3 条等待分析，请等待前面的分析完成。</p>}
      {state.queuePaused && <div className="queue-paused" role="status">
        <p>分析队列已暂停。{state.serverUncertain ? "连接中断或后端忙碌，不能确认服务端任务已结束。" : "本地后端尚未就绪。"}</p>
        {state.serverUncertain && <label><input type="checkbox" checked={confirmedIdle} onChange={e => setConfirmedIdle(e.target.checked)}/>我已检查并确认本地后端已空闲</label>}
        <button className="inline-action" type="button" disabled={state.serverUncertain && !confirmedIdle} onClick={() => { void session.resumeQueue(confirmedIdle); setConfirmedIdle(false); }}>继续排队分析</button>
      </div>}
      {session.resetNotice && <p className="composer-note" role="status">{session.resetNotice}</p>}
      <div
        className="workspace-quick-starts"
        role="group"
        aria-label="选择受控句子"
      >
        {prompts.map((p) => (
          <button
            key={p.prompt_id}
            className="workspace-quick-card"
            type="button"
            disabled={lock}
            aria-pressed={state.prompt?.prompt_id === p.prompt_id}
            onClick={() => dispatch({ type: "PROMPT", prompt: p })}
          >
            <WorkspaceIcon kind="wave" />
            <span>
              <span className="workspace-card-label">选择句子</span>
              <span className="workspace-card-name" lang="ja">
                {TARGETS[p.prompt_id]?.word ?? p.display_text}
              </span>
            </span>
          </button>
        ))}
        {!state.turns.length && <button
          className="workspace-quick-card"
          type="button"
          disabled={lock}
          onClick={() => file.current?.click()}
        >
          <WorkspaceIcon kind="upload" />
          <span>
            <span className="workspace-card-label">上传音频</span>
            <span className="workspace-card-name">WAV</span>
            <span className="workspace-card-format">Mono PCM16 · 8–48 kHz</span>
          </span>
        </button>}
      </div>
      <p className="composer-note">
        仅支持受控句子 · Mono PCM16 WAV · 8–48 kHz · 最长 30
        秒。箭头用于可选实验 X-Ray，可能耗时数分钟；原音、选区与音高观察无需等待它。
      </p>
      <p className="composer-note">音频与手动选区仅保留在当前会话内存，刷新后丢失。点击箭头或“查看音高与同句参考”会把原音发送给本地服务。</p>
      {session.connection && (
        <p className="session-error" role="status">
          {session.connection}
        </p>
      )}
    </section>
  );
}
