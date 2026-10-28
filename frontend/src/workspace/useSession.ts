import { useEffect, useReducer, useRef, useState } from "react";
import { analyze, analysisProgress, cancelAnalysis, loadPrompts, readiness, ApiError } from "../api/client";
import type { Prompt } from "../api/contract";
import { PcmRecorder, type RecordingProvenance, type InputLevel } from "../audio/recorder";
import { ObjectUrls } from "../audio/objectUrls";
import { parseWav } from "../audio/wav";
import { pauseOtherAudio } from "../audio/playback";
import { canSubmit, initialSession, locked, sessionReducer, hasActiveRequest, type Action, type AudioAsset, type Turn } from "../analysis/state";
import { SerialQueue } from "./serialQueue";
import { MVP_PROMPTS, analysisError } from "../analysis/mvp";
export function useSession() {
  const [state, reactDispatch] = useReducer(sessionReducer, initialSession);
  const [prompts, setPrompts] = useState<Prompt[]>(MVP_PROMPTS), [connection, setConnection] = useState("正在连接本地后端；可以先录音或上传，进行手动试听。");
  const [recordingSeconds, setRecordingSeconds] = useState(0), [initializingMic, setInitializingMic] = useState(false);
  const [inputLevel, setInputLevel] = useState<InputLevel | null>(null), [resetNotice, setResetNotice] = useState("");
  const urls = useRef(new ObjectUrls()), recorder = useRef<PcmRecorder | null>(null);
  const busy = useRef(false), current = useRef(state), generation = useRef(0), alive = useRef(true), recordingReady = useRef(false);
  const beforeCapture = useRef<AudioAsset | null>(null), queue = useRef(new SerialQueue<Turn>());
  const activeCancellation = useRef<{ id: number; token: string; confirmed: boolean; controller: AbortController } | null>(null);
  const stopProgressPolling = useRef<(() => void) | null>(null);
  // Update the authoritative ref synchronously, so double clicks/effect scheduling cannot duplicate jobs.
  const dispatch = (action: Action) => { current.current = sessionReducer(current.current, action); reactDispatch(action); };
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    void loadPrompts().then(p => {
      if (!cancelled) setPrompts(MVP_PROMPTS.map(local => p.prompts.find(server => server.prompt_id === local.prompt_id && server.display_text === local.display_text) ?? local));
    }).catch(() => { /* Frozen display list remains usable without the API. */ });
    void readiness().then(() => { if (!cancelled) setConnection(""); })
      .catch(() => { if (!cancelled) setConnection("本地自动分析服务尚未就绪；仍可选句、录音或上传，并手动选择区域试听。"); });
    const cleanup = (reason: string) => {
      alive.current = false;
      stopProgressPolling.current?.();
      pauseOtherAudio(undefined, true); generation.current++;
      void recorder.current?.dispose(reason); urls.current.clear();
    };
    const pagehide = () => cleanup("pagehide");
    window.addEventListener("pagehide", pagehide);
    return () => { cancelled = true; window.removeEventListener("pagehide", pagehide); cleanup("workspace_unmount"); };
  }, []);
  const release = (audio: AudioAsset | null) => {
    if (audio && !current.current.turns.some(t => t.audio.url === audio.url)) urls.current.release(audio.url);
  };
  const discardDraft = () => release(current.current.audio);
  const accept = async (blob: Blob, name: string, token: number, recordingProvenance?: RecordingProvenance) => {
    const parsed = parseWav(await blob.arrayBuffer());
    if (!alive.current || token !== generation.current) return;
    dispatch({ type: "AUDIO", audio: { ...parsed, blob, url: urls.current.create(blob), name,
      ...(recordingProvenance ? { recordingProvenance } : {}) } });
  };
  const fail = (e: unknown) => { if (alive.current) dispatch({ type: "ERROR", message: e instanceof Error ? e.message : "音频操作失败" }); };
  async function upload(file: File) {
    if (busy.current || locked(current.current)) return;
    busy.current = true; pauseOtherAudio(undefined, true); discardDraft();
    const token = ++generation.current;
    dispatch({ type: "PHASE", phase: "VALIDATING_AUDIO" });
    try {
      if (!file.size) throw new Error("音频文件为空，请重新选择 Mono PCM16 WAV（8–48 kHz）。");
      if (file.size > 10 * 1024 * 1024) throw new Error("音频文件超过 10 MiB 上限，请选择较短的 WAV。");
      await accept(file, file.name, token);
    } catch (e) { if (token === generation.current) fail(e); }
    finally { if (token === generation.current) busy.current = false; }
  }
  async function cancelRecording() {
    if (!recorder.current) return;
    const token = ++generation.current, r = recorder.current;
    recorder.current = null; recordingReady.current = false;
    await r.dispose("user_cancel_recording"); // Does not call stop/encodeWav.
    if (!alive.current || token !== generation.current) return;
    busy.current = false; setInitializingMic(false); setRecordingSeconds(0); setInputLevel(null);
    dispatch({ type: "CAPTURE_CANCELLED", audio: beforeCapture.current });
    beforeCapture.current = null;
  }
  async function stop(reason = "user_stop") {
    if (!recordingReady.current) { await cancelRecording(); return; }
    const token = generation.current, r = recorder.current;
    recordingReady.current = false;
    dispatch({ type: "PHASE", phase: "VALIDATING_AUDIO" });
    try {
      const blob = await r!.stop(reason);
      await accept(blob, "浏览器录音.wav", token, r!.getProvenance());
    } catch (e) { if (token === generation.current) fail(e); }
    finally {
      if (recorder.current === r) {
        release(beforeCapture.current); beforeCapture.current = null;
        recorder.current = null; busy.current = false; setInputLevel(null);
      }
    }
  }
  async function record() {
    if (["REQUESTING_MIC", "RECORDING"].includes(current.current.phase)) { await stop(); return; }
    if (busy.current || locked(current.current)) return;
    pauseOtherAudio(undefined, true); busy.current = true;
    beforeCapture.current = current.current.audio; // Retain prior draft until finish or cancellation.
    generation.current++; setRecordingSeconds(0); setInitializingMic(false); setInputLevel(null);
    dispatch({ type: "PHASE", phase: "REQUESTING_MIC" });
    const r = new PcmRecorder(); recorder.current = r;
    const captureFailed = (e: unknown) => {
      if (recorder.current !== r || !alive.current) return;
      release(beforeCapture.current); beforeCapture.current = null;
      recorder.current = null; busy.current = false; recordingReady.current = false;
      setInitializingMic(false); setInputLevel(null); fail(e);
    };
    try {
      const started = await r.start(() => void stop("30_second_limit"), message => {
        void r.dispose("session_capture_error"); captureFailed(new Error(message));
      }, seconds => { if (alive.current && recorder.current === r) setRecordingSeconds(seconds); },
      () => { if (alive.current && recorder.current === r) setInitializingMic(true); },
      level => { if (alive.current && recorder.current === r) setInputLevel(level); });
      if (started && recorder.current === r && alive.current) {
        recordingReady.current = true; setInitializingMic(false); dispatch({ type: "CAPTURE_STARTED" });
      }
    } catch (e) { captureFailed(e); }
  }
  const kickQueue = () => void queue.current.kick(
    () => alive.current && !current.current.queuePaused ? current.current.turns.find(t => t.status === "QUEUED") : undefined,
    async turn => {
      const control = { id: turn.id, token: crypto.randomUUID(), confirmed: false, controller: new AbortController() };
      activeCancellation.current = control;
      dispatch({ type: "REQUEST_STARTED", id: turn.id, at: performance.now() });
      const pollController = new AbortController();
      let pollTimer: number | undefined;
      const stopPolling = () => { pollController.abort(); window.clearTimeout(pollTimer); };
      stopProgressPolling.current = stopPolling;
      const poll = async () => {
        if (!alive.current || pollController.signal.aborted) return;
        try {
          const progress = await analysisProgress(control.token, pollController.signal);
          if (!pollController.signal.aborted && alive.current && activeCancellation.current === control && progress.state !== "NOT_FOUND")
            dispatch({ type: "PROGRESS", id: turn.id, progress });
        } catch {
          if (!pollController.signal.aborted && alive.current && activeCancellation.current === control)
            dispatch({ type: "PROGRESS", id: turn.id, message: "阶段信息暂不可用，分析仍在等待。" });
        }
        if (!pollController.signal.aborted && alive.current) pollTimer = window.setTimeout(() => void poll(), 2000);
      };
      // Only the serial driver's active request polls; queued Turns never do.
      pollTimer = window.setTimeout(() => void poll(), 1000);
      try {
        const response = await analyze(turn.prompt.prompt_id, turn.audio.blob, undefined, control.token, control.controller.signal);
        if (alive.current) {
          dispatch(control.confirmed ? { type: "CANCEL_CONFIRMED", id: turn.id, at: performance.now() }
            : { type: "RESULT", id: turn.id, response, at: performance.now() });
          setResetNotice("");
        }
      } catch (e) {
        if (!alive.current) return;
        if (control.confirmed || e instanceof ApiError && e.code === "ANALYSIS_CANCELLED") {
          dispatch({ type: "CANCEL_CONFIRMED", id: turn.id, at: performance.now() });
          setResetNotice(""); return;
        }
        const unknown = !(e instanceof ApiError) || ["NETWORK_ERROR", "HTTP_ERROR", "SERVICE_BUSY"].includes(e.code);
        const unavailable = e instanceof ApiError && ["ALIGNMENT_RUNTIME_UNAVAILABLE", "REFERENCE_ARTIFACT_MISSING"].includes(e.code);
        dispatch({ type: "TURN_ERROR", id: turn.id, at: performance.now(), pause: unknown || unavailable, uncertain: unknown,
          errorCode: e instanceof ApiError ? e.code : "NETWORK_ERROR",
          message: e instanceof ApiError ? `${analysisError(e.code)}（${e.code}；请求 ${e.requestId || "未取得"}）` : analysisError("NETWORK_ERROR") });
        if (!unknown) setResetNotice("");
      } finally {
        stopPolling();
        if (stopProgressPolling.current === stopPolling) stopProgressPolling.current = null;
        if (activeCancellation.current === control) activeCancellation.current = null;
      }
    });
  async function cancelTurn(id: number) {
    const control = activeCancellation.current;
    if (!control || control.id !== id || current.current.turns.find(t => t.id === id)?.cancelRequested) return;
    dispatch({ type: "CANCEL_REQUESTED", id });
    try {
      const deadline = performance.now() + 10000;
      while (alive.current && activeCancellation.current === control) {
        const result = await cancelAnalysis(control.token);
        if (result.status === "CANCELLED") {
          control.confirmed = true;
          // Abort only after the server explicitly confirms worker cleanup; never
          // treat a client-side fetch abort as proof that server computation stopped.
          control.controller.abort(); return;
        }
        if (result.status !== "NOT_FOUND") return; // Original request settles only after cleanup.
        if (performance.now() >= deadline) throw new Error("后端尚未登记本次请求，未能确认取消，请稍后重试。");
        await new Promise(resolve => window.setTimeout(resolve, 100));
      }
    } catch (e) {
      if (alive.current && activeCancellation.current === control)
        dispatch({ type: "CANCEL_FAILED", id, message: `未能确认取消，原分析仍在等待：${e instanceof Error ? e.message : String(e)}` });
    }
  }
  function submit() {
    if (busy.current || !canSubmit(current.current)) return;
    pauseOtherAudio(undefined, true); dispatch({ type: "START" }); kickQueue();
  }
  function cancelQueued(id: number) {
    const turn = current.current.turns.find(t => t.id === id && t.status === "QUEUED");
    if (!turn) return;
    dispatch({ type: "CANCEL_QUEUED", id }); urls.current.release(turn.audio.url);
  }
  async function resumeQueue(confirmedIdle: boolean) {
    if (current.current.serverUncertain && !confirmedIdle) return;
    try { await readiness(); dispatch({ type: "RESUME_QUEUE" }); setResetNotice(""); kickQueue(); }
    catch (e) { setResetNotice(`后端尚未就绪：${e instanceof Error ? e.message : String(e)}`); }
  }
  function reset() {
    if (queue.current.running || hasActiveRequest(current.current) || current.current.serverUncertain) {
      setResetNotice("本地后端仍在分析或状态无法确认，不能取消服务端任务。请等待完成；连接中断时须先确认后端已空闲。"); return false;
    }
    pauseOtherAudio(undefined, true); generation.current++; void recorder.current?.dispose("new_analysis_reset");
    recorder.current = null; beforeCapture.current = null; recordingReady.current = false;
    setInitializingMic(false); setRecordingSeconds(0); setInputLevel(null); setResetNotice("");
    busy.current = false; urls.current.clear(); dispatch({ type: "RESET" }); return true;
  }
  function retry(prompt: Prompt) {
    if (busy.current || locked(current.current)) return;
    pauseOtherAudio(undefined, true); discardDraft(); dispatch({ type: "RETRY", prompt });
  }
  return { state, dispatch, prompts, connection, recordingSeconds, initializingMic, inputLevel, resetNotice,
    upload, record, stop, cancelRecording, submit, reset, retry, cancelQueued, cancelTurn, resumeQueue };
}
