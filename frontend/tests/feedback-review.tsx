// Dev-server-only review fixture. Not linked by App and not included in Vite build.
import { createRoot } from "react-dom/client";
import { useState } from "react";
import { AnalysisStream } from "../src/workspace/AnalysisStream";
import { WorkspaceEmpty } from "../src/WorkspaceEmpty";
import { parseWav } from "../src/audio/wav";
import { STAGES } from "../src/api/progress";
import type { Turn } from "../src/analysis/state";
import type { SpeechXRayAnalysisResponse } from "../src/api/contract";
import fixture from "../../data/examples/api-v1-analysis-response.json";
import "../src/landing.css";
import "../src/workspace.css";
import "../src/workspace/integration.css";
const scene = new URLSearchParams(location.search).get("scene") ?? "reduced";
if (scene === "queue-record") {
  // Explicit synthetic device + pending HTTP fixture: tests useSession's full
  // queue/capture lifecycle without microphone permissions or human audio.
  const fetchOriginal = window.fetch.bind(window);
  let pending: ((response: Response) => void) | undefined, key = "";
  window.fetch = async (input, init) => {
    const path = String(input);
    if (path.endsWith("/api/v1/analyses")) {
      key = new Headers(init?.headers).get("X-Analysis-Token")!;
      return new Promise(resolve => { pending = resolve; });
    }
    if (path.includes("/analyses/progress/")) return Response.json({request_key:key,request_id:"synthetic-queue-review",stage_index:4,stage_label:STAGES[3],updated_at:new Date().toISOString(),state:"RUNNING",history:STAGES.slice(0,4).map((stage_label,i)=>({stage_index:i+1,stage_label,updated_at:new Date().toISOString()}))});
    if (path.includes("/analyses/cancel/")) { pending?.(Response.json({error_code:"ANALYSIS_CANCELLED",message:"Synthetic fixture cancelled"},{status:409}));return Response.json({status:"CANCELLED"}); }
    return fetchOriginal(input, init);
  };
  navigator.mediaDevices.getUserMedia = async () => {
    const context = new AudioContext({sampleRate:48000}); await context.resume();
    const oscillator=context.createOscillator(), destination=context.createMediaStreamDestination();
    oscillator.frequency.value=220;oscillator.connect(destination);oscillator.start();
    const track=destination.stream.getAudioTracks()[0], originalStop=track.stop.bind(track);
    track.stop=()=>{originalStop();oscillator.stop();oscillator.disconnect();void context.close();};
    return destination.stream;
  };
}
const blob = await (await fetch("/audio/reference/learner-v1-001.wav")).blob();
const audio = { ...parseWav(await blob.arrayBuffer()), blob, url: URL.createObjectURL(blob), name: "synthetic review audio" };
const response = structuredClone(fixture) as SpeechXRayAnalysisResponse;
const target = response.targets[0];
target.availability.duration = true; target.availability.reference = true; target.availability.deviation = true; target.availability.realization = true;
target.deviation!.direction = "BELOW_REFERENCE_MEDIAN";
target.duration!.rate_normalized_duration = 1.5; target.duration!.rate_normalized_duration_per_mora = .75;
target.deviation!.signed_delta = -.5; target.deviation!.ratio_to_median = .75;
target.realization!.selected_variant = "REDUCED_SELECTED"; target.realization!.evidence_status = "AVAILABLE";
if (scene === "no-alignment") {
  response.status = "ABSTAINED"; response.timeline = null;
  target.time_span = null; target.duration = null; target.reference = null;
  target.deviation = null; target.realization = null; target.acoustics = null;
  target.availability = {duration:false,reference:false,deviation:false,realization:false,raw_f0:false,rms:false};
  target.evidence_status = "ABSTAINED";
  target.reasons = [{stage:"ALIGNED",reason_code:"ALIGNMENT_UNUSABLE",message:"Declared target evidence is unavailable."}];
}
const stage = scene === "stage1" ? 1 : 4;
const resultScene = scene === "reduced" || scene === "no-alignment";
const turn: Turn = {id: 1, prompt: response.prompt, audio, status: resultScene ? response.status : "ANALYZING", ...(resultScene ? {response} : {requestStartedAt: performance.now(), progress: {
  request_key: "explicit-visual-fixture",request_id: "explicit-visual-fixture",stage_index:stage,stage_label:STAGES[stage-1],updated_at:new Date().toISOString(),state:"RUNNING" as const,
  history:STAGES.slice(0,stage).map((stage_label,i)=>({stage_index:i+1,stage_label,updated_at:new Date().toISOString()})),
}})};
function Review() {
  const [expanded,setExpanded]=useState<number|null>(1);
  return <div className="workspace-empty" style={{display:"block",maxWidth:860,margin:"0 auto",padding:"24px"}}>
    <p role="note" style={{position:"sticky",top:0,background:"white",zIndex:10,padding:"8px 0"}}>工程 UI Fixture · {scene} · 非真人诊断，非实时 backend receipt</p>
    <AnalysisStream turns={[turn]} expanded={expanded} onToggle={id=>setExpanded(expanded===id?null:id)} playbackDisabled={false} onRetry={()=>{}} onCancelQueued={()=>{}} onCancelTurn={()=>{}} onSelection={()=>{}} />
  </div>;
}
createRoot(document.getElementById("root")!).render(scene === "queue-record" ? <><p style={{position:"fixed",top:62,right:24,zIndex:20,background:"white"}}>工程 Fixture：合成录音 + 挂起 HTTP；无实体麦克风</p><WorkspaceEmpty/></> : <Review/>);
