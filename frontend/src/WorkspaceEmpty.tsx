import { useEffect, useId, useRef, useState } from "react";
import { Plus, WorkspaceIcon } from "./components/Icons";
import { useSession } from "./workspace/useSession";
import { Composer } from "./workspace/Composer";
import { AnalysisStream } from "./workspace/AnalysisStream";
import { locked, hasActiveRequest } from "./analysis/state";
import { pauseOtherAudio } from "./audio/playback";
import type { Turn } from "./analysis/state";
import { InterviewDemo } from "./demo/InterviewDemo";
import { DEMOS, demoFromHash } from "./demo/loadDemo";

function WorkspaceSidebar({
  onNewAnalysis,
  busy,
  turns,
  demoId,
  onDemo,
  demoDisabled,
  onHistory,
}: {
  onNewAnalysis: () => void;
  busy: boolean;
  turns: Turn[];
  demoId: string | null;
  onDemo: (id: string) => void;
  demoDisabled: boolean;
  onHistory: (id: number) => void;
}) {
  const historyTitleId = useId();
  return (
    <aside className="workspace-sidebar" aria-label="工作区侧栏">
      <button
        className="workspace-new"
        type="button"
        title={busy ? "服务端任务尚未结束，点击查看重置说明" : undefined}
        onClick={onNewAnalysis}
      >
        <Plus /> 新分析
      </button>
      <section className="workspace-history" aria-labelledby={historyTitleId}>
        <h2 id={historyTitleId}>当前会话</h2>
        <ul>
          {turns.map((turn) => (
            <li key={turn.id}>
              <button
                type="button"
                className="workspace-history-row"
                aria-label={`查看分析 ${turn.id}：${turn.prompt.display_text}`}
                title={turn.prompt.display_text}
                onClick={() => onHistory(turn.id)}
              >
                <span className="workspace-history-marker">
                  <WorkspaceIcon kind="wave" />
                </span>
                <span className="workspace-demo-tag">{String(turn.id).padStart(2, "0")}</span>
                <span className="workspace-history-text" lang="ja">
                  {turn.prompt.display_text}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {!turns.length && <p className="composer-note">提交后保留在本次会话；刷新后清空。</p>}
      </section>
      <section className="workspace-history workspace-demo-list" aria-label="DEMO 演示">
        <h2>DEMO · 演示</h2>
        <ul>{DEMOS.map(({ prompt, label }) => <li key={prompt.prompt_id}>
          <button type="button" className="workspace-history-row" disabled={demoDisabled} aria-pressed={demoId === prompt.prompt_id}
            aria-label={`打开 DEMO：${label}`} onClick={() => onDemo(prompt.prompt_id)}>
            <span className="workspace-history-marker"><WorkspaceIcon kind="wave"/></span>
            <span className="workspace-demo-tag">Demo</span><span className="workspace-history-text" lang="ja">{label}</span>
          </button>
        </li>)}</ul>
        <p className="composer-note">合成音频 · 已保存的完整分析</p>
      </section>
      <button
        className="workspace-settings"
        type="button"
        aria-disabled="true"
        disabled
        aria-label="设置（静态预览）"
      >
        <WorkspaceIcon kind="settings" /> 设置
      </button>
    </aside>
  );
}

export function WorkspaceEmpty() {
  const session = useSession();
  const drawer = useRef<HTMLDialogElement>(null);
  const help = useRef<HTMLDialogElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [demoId, setDemoId] = useState<string | null>(() => demoFromHash(window.location.hash));
  const returnToPractice = () => { pauseOtherAudio(); setDemoId(null); };
  const openDemo = (id: string) => {
    if (locked(session.state)) return;
    pauseOtherAudio(); setDemoId(id); drawer.current?.close();
    document.getElementById("workspace-main")?.focus({ preventScroll: true });
  };
  const onHistory = (id: number) => {
    returnToPractice(); drawer.current?.close();
    window.requestAnimationFrame(() => document.getElementById(`analysis-turn-${id}`)?.scrollIntoView({ block: "start", behavior: "instant" }));
  };
  const resetEmpty = () => {
    if (!session.reset()) { returnToPractice(); return; }
    returnToPractice();
    drawer.current?.close();
    document.getElementById("workspace-main")?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px)");
    const closeOnDesktop = () => {
      if (desktop.matches) drawer.current?.close();
    };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  return (
    <div
      className={`workspace-empty ${session.state.turns.length || demoId ? "has-turns" : ""}`}
    >
      <a
        className="skip-link"
        href="#/workspace"
        onClick={(event) => {
          event.preventDefault();
          resetEmpty();
        }}
      >
        跳至主要内容
      </a>
      <header className="workspace-header">
        <a className="workspace-brand" href="#top">
          Japanese Speech X-Ray
        </a>
        <div className="workspace-header-actions">
          <button
            className="workspace-help"
            type="button"
            aria-label="帮助"
            onClick={() => help.current?.showModal()}
          >
            <WorkspaceIcon kind="help" />
            <span>帮助</span>
          </button>
          <button
            className="workspace-account"
            type="button"
            aria-disabled="true"
            disabled
            aria-label="用户账户（静态预览）"
          >
            <WorkspaceIcon kind="user" />
          </button>
          <button
            className="workspace-menu"
            type="button"
            aria-label="打开侧栏"
            aria-expanded={menuOpen}
            aria-controls="workspace-drawer"
            onClick={() => {
              drawer.current?.showModal();
              setMenuOpen(true);
            }}
          >
            <WorkspaceIcon kind="menu" />
          </button>
        </div>
      </header>
      <div className="workspace-desktop-sidebar">
        <WorkspaceSidebar
          onNewAnalysis={resetEmpty}
          busy={hasActiveRequest(session.state) || session.state.serverUncertain}
          turns={session.state.turns}
          demoId={demoId} onDemo={openDemo} demoDisabled={locked(session.state)} onHistory={onHistory}
        />
      </div>
      <main
        className="workspace-main"
        id="workspace-main"
        tabIndex={-1}
        aria-labelledby="workspace-title"
        onPlayCapture={(event) => {
          // One audible recording at a time; each Turn still owns its own audio.
          pauseOtherAudio(event.target as HTMLAudioElement);
        }}
      >
        <div className="workspace-welcome">
          <h1 id="workspace-title">Japanese Speech X-Ray</h1>
          <p className="workspace-subtitle">
            说一句日语，看看发音内部发生了什么。
          </p>
          {demoId ? <InterviewDemo key={demoId} promptId={demoId} onReturn={returnToPractice} onPractice={prompt => {
            returnToPractice(); session.retry(prompt);
          }}/> : <><AnalysisStream
            turns={session.state.turns}
            expanded={session.state.expanded}
            onToggle={(id) => session.dispatch({ type: "EXPAND", id })}
            playbackDisabled={locked(session.state)}
            onRetry={session.retry}
            onCancelQueued={session.cancelQueued}
            onCancelTurn={session.cancelTurn}
            onSelection={(turnId, selection) => session.dispatch({ type: "SELECTION", turnId, selection })}
          />
          <Composer session={session} />
          </>}
        </div>
      </main>
      <dialog
        ref={drawer}
        id="workspace-drawer"
        className="workspace-drawer"
        aria-labelledby="drawer-title"
        onClose={() => setMenuOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) drawer.current?.close();
        }}
        onKeyDown={(event) => {
          // Keep Tab at the drawer edges inside the page, including preview buttons.
          if (event.key !== "Tab") return;
          const buttons =
            event.currentTarget.querySelectorAll<HTMLButtonElement>(
              "button:not(:disabled)",
            );
          const first = buttons[0];
          const last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <div className="workspace-drawer-header">
          <h2 id="drawer-title">工作区</h2>
          <button
            type="button"
            className="workspace-drawer-close"
            aria-label="关闭侧栏"
            onClick={() => drawer.current?.close()}
          >
            <WorkspaceIcon kind="close" />
          </button>
        </div>
        <WorkspaceSidebar
          onNewAnalysis={resetEmpty}
          busy={hasActiveRequest(session.state) || session.state.serverUncertain}
          turns={session.state.turns}
          demoId={demoId} onDemo={openDemo} demoDisabled={locked(session.state)} onHistory={onHistory}
        />
      </dialog>
      <dialog ref={help} className="workspace-help-dialog" aria-label="练习与隐私说明">
        <h2>如何练习</h2>
        <p>先选择固定句子。左侧 + 上传 WAV；小麦克风开始 / 停止录音。原音、波形、选区与音高观察无需等待自动对齐。</p>
        <p>录音或上传后即可试听原音、查看波形。拖动框选或输入起止毫秒，点击试听 / 循环；不用等自动分析。试听确认词区域只表示用户确认词范围，不验证内部长元音边界。</p>
        <p>点击“查看音高与同句参考”观察可用音高片段，并听 Haruka 合成朗读，再次录音练习。Haruka 合成参考 · 非母语者准确性标准。当前不提供发音评分或音高重音正确性判定。</p>
        <p>蓝色箭头进入可选实验 X-Ray，可能需要数分钟。使用真实阶段进度和取消；队列保留 1 条分析 + 3 条等待，取消须后台确认。失败后仍可手动练习。</p>
        <p>音频与选区保留在浏览器当前会话内存，刷新后丢失。点击箭头或音高提取按钮会把原音发送到本地服务，不发送云推理 API；服务临时文件按请求生命周期清理，不默认保留用户音频。</p>
        <button type="button" className="inline-action" onClick={() => help.current?.close()}>关闭帮助</button>
      </dialog>
    </div>
  );
}
