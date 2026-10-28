import { useEffect, useRef, useState } from "react";
import type { Prompt } from "../api/contract";
import type { Turn } from "../analysis/state";
import type { AudioSelection } from "../audio/selection";
import { loadDemo } from "./loadDemo";
import { AnalysisStream } from "../workspace/AnalysisStream";
import "./demo.css";

export function InterviewDemo({ promptId, onReturn, onPractice }: { promptId: string; onReturn: () => void; onPractice: (prompt: Prompt) => void }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof loadDemo>> | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0), [expanded, setExpanded] = useState(true);
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let url: string | undefined, active = true, timedOut = false;
    setError(""); setData(null); setTurn(null);
    const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
    void loadDemo(promptId, controller.signal).then(payload => {
      if (!active || controller.signal.aborted) return;
      url = URL.createObjectURL(payload.audio.blob);
      setData(payload);
      setTurn({ id: 1, prompt: payload.prompt, audio: { ...payload.audio, url }, response: payload.response, status: "COMPLETED" });
    }).catch(e => {
      if (active && (!controller.signal.aborted || timedOut)) setError(timedOut ? "DEMO 读取超时，请重试。" : e instanceof TypeError ? "无法读取 DEMO 文件，请检查本地页面服务后重试。" : e instanceof Error ? e.message : "DEMO 暂时无法读取。");
    }).finally(() => { clearTimeout(timer); controller.abort(); });
    return () => { active = false; controller.abort(); clearTimeout(timer); if (url) URL.revokeObjectURL(url); };
  }, [promptId, attempt]);
  const selection = (_id: number, selection: AudioSelection) => setTurn(t => t && ({ ...t, audio: { ...t.audio, selection } }));
  return <section ref={section} className="interview-demo" aria-label="演示">
    <header className="demo-heading">
      <div><strong>DEMO · 演示</strong><p>Haruka 合成音频 · 预计算 pYIN 音高与 MFA 分析</p></div>
      <button type="button" className="inline-action" onClick={onReturn}>返回我的练习</button>
    </header>
    <p className="demo-source">这是已保存的合成音频分析，非本次录音。原音与同句参考使用同一 Haruka WAV，曲线相同用于展示交互，不表示真人发音表现或准确性标准。</p>
    {turn && expanded && <nav className="demo-sections" aria-label="四段演示内容">
      {[["01 · 原音与波形", ".audio-inspector"], ["02 · 音高与语调", ".prosody-panel"], ["03 · 练习建议", ".practice-next"], ["04 · 实验 X-Ray", ".experimental-details"]].map(([label, selector]) =>
        <button key={selector} type="button" onClick={() => section.current?.querySelector(selector)?.scrollIntoView({ block: "start", behavior: "instant" })}>{label}</button>)}
    </nav>}
    {!turn && !error && <p role="status">正在读取 DEMO……</p>}
    {error && <p className="session-error" role="alert">{error} <button type="button" className="inline-action" onClick={() => setAttempt(n => n + 1)}>重试加载</button></p>}
    {turn && data && <AnalysisStream turns={[turn]} expanded={expanded ? 1 : null} onToggle={() => setExpanded(!expanded)} playbackDisabled={false}
      onRetry={onPractice} onCancelQueued={() => {}} onCancelTurn={() => {}} onSelection={selection} demoCurves={data.curves}/>}
  </section>;
}
