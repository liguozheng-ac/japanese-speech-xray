import type { Prompt, SpeechXRayAnalysisResponse } from "../api/contract";
import type { WavAudio } from "../audio/wav";
import type { RecordingProvenance } from "../audio/recorder";
import type { AnalysisProgress } from "../api/progress";
import type { AudioSelection } from "../audio/selection";
export type AudioAsset = WavAudio & { blob: Blob; url: string; name: string; recordingProvenance?: RecordingProvenance; selection?: AudioSelection };
// Composer state is independent of submitted Turns.
export type Phase = "IDLE" | "PROMPT_SELECTED" | "VALIDATING_AUDIO" | "REQUESTING_MIC" | "RECORDING" | "AUDIO_READY" | "ERROR";
export type Turn = {
  id: number; prompt: Prompt; audio: AudioAsset;
  status: "QUEUED" | "ANALYZING" | "COMPLETED" | "PARTIAL_EVIDENCE" | "ABSTAINED" | "ERROR" | "CANCELLED";
  cancelRequested?: boolean; cancelError?: string;
  progress?: AnalysisProgress; progressError?: string;
  response?: SpeechXRayAnalysisResponse; error?: string; errorCode?: string;
  requestStartedAt?: number; requestEndedAt?: number;
};
export type Session = {
  phase: Phase; prompt: Prompt | null; audio: AudioAsset | null;
  turns: Turn[]; nextTurnId: number; expanded: number | null;
  composerOpen: boolean; error: string | null;
  queuePaused: string | null; serverUncertain: boolean;
};
export const initialSession: Session = {
  phase: "IDLE", prompt: null, audio: null, turns: [], nextTurnId: 1,
  expanded: null, composerOpen: true, error: null, queuePaused: null, serverUncertain: false,
};
export const QUEUE_LIMIT = 3;
export const queuedCount = (s: Session) => s.turns.filter(t => t.status === "QUEUED").length;
export const hasActiveRequest = (s: Session) => s.turns.some(t => t.status === "ANALYZING");
export const locked = (s: Session) => ["REQUESTING_MIC", "RECORDING", "VALIDATING_AUDIO"].includes(s.phase);
export const canSubmit = (s: Session) => s.phase === "AUDIO_READY" && !!s.prompt && !!s.audio && queuedCount(s) < QUEUE_LIMIT;
export type Action =
  | { type: "SELECTION"; selection: AudioSelection; turnId?: number }
  | { type: "PROGRESS"; id: number; progress?: AnalysisProgress; message?: string }
  | { type: "PROMPT"; prompt: Prompt }
  | { type: "PHASE"; phase: "REQUESTING_MIC" | "VALIDATING_AUDIO" }
  | { type: "CAPTURE_STARTED" }
  | { type: "CAPTURE_CANCELLED"; audio: AudioAsset | null }
  | { type: "AUDIO"; audio: AudioAsset }
  | { type: "START" }
  | { type: "REQUEST_STARTED"; id: number; at: number }
  | { type: "RESULT"; id: number; response: SpeechXRayAnalysisResponse; at: number }
  | { type: "TURN_ERROR"; id: number; message: string; errorCode?: string; at: number; pause?: boolean; uncertain?: boolean }
  | { type: "ERROR"; message: string }
  | { type: "CANCEL_QUEUED"; id: number }
  | { type: "CANCEL_REQUESTED"; id: number }
  | { type: "CANCEL_FAILED"; id: number; message: string }
  | { type: "CANCEL_CONFIRMED"; id: number; at: number }
  | { type: "RESUME_QUEUE" }
  | { type: "RETRY"; prompt: Prompt }
  | { type: "EXPAND"; id: number }
  | { type: "CONTINUE" }
  | { type: "RESET" };
export function sessionReducer(s: Session, a: Action): Session {
  switch (a.type) {
    case "SELECTION":
      return a.turnId == null ? { ...s, audio: s.audio ? { ...s.audio, selection: a.selection } : null }
        : { ...s, turns: s.turns.map(t => t.id === a.turnId ? { ...t, audio: { ...t.audio, selection: a.selection } } : t) };
    case "PROGRESS":
      return { ...s, turns: s.turns.map(t => t.id === a.id && t.status === "ANALYZING" ? { ...t, progress: a.progress ?? t.progress, progressError: a.message } : t) };
    case "CANCEL_REQUESTED":
      return { ...s, turns: s.turns.map(t => t.id === a.id && t.status === "ANALYZING" ? { ...t, cancelRequested: true, cancelError: undefined } : t) };
    case "CANCEL_FAILED":
      return { ...s, turns: s.turns.map(t => t.id === a.id && t.status === "ANALYZING" ? { ...t, cancelRequested: false, cancelError: a.message } : t) };
    case "CANCEL_CONFIRMED":
      return { ...s, turns: s.turns.map(t => t.id === a.id && t.status === "ANALYZING" ? { ...t, status: "CANCELLED", cancelRequested: false, cancelError: undefined, requestEndedAt: a.at } : t) };
    case "REQUEST_STARTED":
      if (hasActiveRequest(s) || s.queuePaused || s.turns.find(t => t.status === "QUEUED")?.id !== a.id) return s;
      return { ...s, turns: s.turns.map(t => t.id === a.id ? { ...t, status: "ANALYZING", requestStartedAt: a.at } : t) };
    case "RESULT":
      if (!s.turns.some(t => t.id === a.id && t.status === "ANALYZING")) return s;
      return { ...s, expanded: a.id, turns: s.turns.map(t => t.id === a.id ? { ...t, status: a.response.status, response: a.response, requestEndedAt: a.at } : t) };
    case "TURN_ERROR":
      if (!s.turns.some(t => t.id === a.id && t.status === "ANALYZING")) return s;
      return { ...s, queuePaused: a.pause ? a.message : s.queuePaused, serverUncertain: !!a.uncertain || s.serverUncertain,
        turns: s.turns.map(t => t.id === a.id ? { ...t, status: "ERROR", error: a.message, errorCode: a.errorCode, requestEndedAt: a.at } : t) };
    case "CANCEL_QUEUED":
      return { ...s, turns: s.turns.filter(t => t.id !== a.id || t.status !== "QUEUED") };
    case "RESUME_QUEUE": return { ...s, queuePaused: null, serverUncertain: false };
    case "EXPAND": return { ...s, expanded: s.expanded === a.id ? null : a.id };
    case "RESET": return hasActiveRequest(s) || s.serverUncertain ? s : initialSession;
    case "CAPTURE_STARTED": return s.phase === "REQUESTING_MIC" ? { ...s, phase: "RECORDING" } : s;
    case "CAPTURE_CANCELLED":
      return { ...s, audio: a.audio, phase: a.audio && s.prompt ? "AUDIO_READY" : s.prompt ? "PROMPT_SELECTED" : "IDLE", error: null };
    case "ERROR": return { ...s, phase: "ERROR", audio: null, error: a.message };
    case "AUDIO": return { ...s, audio: a.audio, phase: s.prompt ? "AUDIO_READY" : "IDLE", error: null };
    case "PHASE": return { ...s, phase: a.phase, audio: null, error: null };
  }
  if (locked(s)) return s;
  switch (a.type) {
    case "PROMPT": return { ...s, prompt: a.prompt,
      audio: s.audio && s.prompt?.prompt_id !== a.prompt.prompt_id ? { ...s.audio, selection: undefined } : s.audio,
      phase: s.audio ? "AUDIO_READY" : "PROMPT_SELECTED", error: null };
    case "RETRY": return { ...s, prompt: a.prompt, audio: null, phase: "PROMPT_SELECTED", error: null };
    case "START":
      if (!canSubmit(s)) return s;
      return { ...s, phase: "IDLE", prompt: null, audio: null, nextTurnId: s.nextTurnId + 1, error: null,
        turns: [...s.turns, { id: s.nextTurnId, status: "QUEUED", prompt: s.prompt!, audio: s.audio! }] };
    case "CONTINUE": return { ...s, phase: "IDLE", prompt: null, audio: null, error: null };
    default: return s;
  }
}
