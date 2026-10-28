import { useCallback, useEffect, useRef, useState } from "react";
import manifest from "../../public/audio/reference/manifest.json";
import { pauseOtherAudio } from "../audio/playback";
import { elapsedLabel } from "./elapsed";
import { TARGETS } from "../analysis/mvp";

export function ReferenceReading({ promptId, disabled }: { promptId: string; disabled: boolean }) {
  const asset = manifest.assets.find(a => a.prompt_id === promptId);
  const audio = useRef<HTMLAudioElement>(null);
  const bindAudio = useCallback((node: HTMLAudioElement | null) => {
    // Ref detachment runs while the old element is still available.
    // Pause it explicitly instead of relying on DOM removal to stop playback.
    if (audio.current && audio.current !== node) {
      audio.current.pause();
      audio.current.currentTime = 0;
    }
    audio.current = node;
  }, []);
  const [playing, setPlaying] = useState(false), [time, setTime] = useState(0), [error, setError] = useState("");
  useEffect(() => {
    if (disabled && audio.current) { audio.current.pause(); audio.current.currentTime = 0; setTime(0); }
  }, [disabled]);
  useEffect(() => { setPlaying(false); setTime(0); setError(""); }, [promptId]);
  const available = asset?.status === "READY" && asset.path;
  const label = asset?.type === "human" ? "参考朗读 · 真人录音" : "参考朗读 · 合成语音";
  const native = TARGETS[promptId];
  return <span className="reference-reading">
    <button type="button" disabled={disabled || !available} className="audio-play"
      aria-label={`${playing ? "暂停" : "播放"}${label}`} onClick={() => {
        const a = audio.current;
        if (!a) return;
        if (!a.paused) a.pause();
        else {
          pauseOtherAudio(a);
          if (a.ended) a.currentTime = 0;
          setError("");
          void a.play().catch(() => setError("参考朗读暂时无法播放，请重新尝试。"));
        }
      }}>{playing ? "Ⅱ" : "▶"} {label}{playing ? ` ${elapsedLabel(0, time * 1000)}` : ""}</button>
    {available ? <audio key={promptId} ref={bindAudio} data-reference-reading="true" preload="metadata"
      src={`${import.meta.env.BASE_URL}${asset.path}`} onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
      onTimeUpdate={e => setTime(e.currentTarget.currentTime)} onError={() => setError("参考朗读资源加载失败。")}/>
      : <small>朗读音频待准备</small>}
    {error && <small role="alert">{error}</small>}
    <details className="reading-source"><summary>朗读来源与限制</summary>
      <p>当前可播放资源：{asset?.voice ?? "未提供来源"} · {asset?.engine ?? "无资源"}。{asset?.type === "synthetic" ? "合成朗读辅助，不是母语者实录，也不参与 JVS 统计。" : "仅作为本地朗读辅助。"}</p>
      {asset && <p lang="ja">播放原文：{asset.text}</p>}
      {native && <><p>母语者参考源：JVS parallel100 · {native.context}</p><p lang="ja">实际原句：{native.sentence}</p>
        <p>母语者材料在另一句实际语境中，供词语发音参考，不代表严格等价的时长标准。当前正式接口未提供原生参考音频读取，未从私有研究页面接入音频；可继续原音与手动练习。</p>
        <p>公开参考音频：许可审核待完成。本次不打包或公开 JVS 原音。</p></>}
    </details>
  </span>;
}
