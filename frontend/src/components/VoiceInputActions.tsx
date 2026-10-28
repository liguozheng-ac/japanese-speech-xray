import { Arrow, Mic } from "./Icons";
import "./VoiceInputActions.css";

/** Shared decorative input actions for the landing and empty workspace. */
export function VoiceInputActions({ onActivate }: { onActivate?: () => void }) {
  return (
    <div className="voice-input-actions">
      <button type="button" className="voice-input-mic" aria-label="进入工作区录音" onClick={onActivate}>
        <Mic />
      </button>
      <button type="button" className="voice-input-trigger" aria-label="进入分析工作区" onClick={onActivate}>
        <Arrow />
      </button>
    </div>
  );
}
