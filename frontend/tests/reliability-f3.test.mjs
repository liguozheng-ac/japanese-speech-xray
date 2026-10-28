import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
import ts from 'typescript';
async function module(path) {
  const source = fs.readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext} }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
}
const {initialSession,sessionReducer:r,canSubmit,hasActiveRequest,queuedCount,locked}=await module('analysis/state.ts');
const {SerialQueue}=await module('workspace/serialQueue.ts');
const {autoFitPeaks}=await module('audio/display.ts');
const {encodeWav,parseWav,waveformPeaks}=await module('audio/wav.ts');
const response=JSON.parse(fs.readFileSync(new URL('../../data/examples/api-v1-analysis-response.json',import.meta.url),'utf8'));
const prompt=response.prompt, audio={url:'blob:a',blob:new Blob(['exact-input']),durationMs:1000};
const draft=s=>r(r(s,{type:'PROMPT',prompt}),{type:'AUDIO',audio});
const enqueue=s=>r(draft(s),{type:'START'});
const begin=(s,id)=>r(s,{type:'REQUEST_STARTED',id,at:100});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('inflight result and error cannot overwrite the next recording or AUDIO_READY draft',()=>{
  for(const end of [{type:'RESULT',id:1,response,at:200},{type:'TURN_ERROR',id:1,message:'failed',at:200}]) {
    let s=begin(enqueue(initialSession),1);
    assert.ok(hasActiveRequest(s));assert.ok(!locked(s));
    s=r(s,{type:'PROMPT',prompt});s=r(s,{type:'PHASE',phase:'REQUESTING_MIC'});s=r(s,{type:'CAPTURE_STARTED'});
    s=r(s,end);assert.equal(s.phase,'RECORDING');assert.equal(s.prompt,prompt);
    s=r(s,{type:'AUDIO',audio});assert.ok(canSubmit(s));
  }
});
test('FIFO, three queued limit, cancel creates ID hole and never cancels inflight',()=>{
  let s=begin(enqueue(initialSession),1);
  s=enqueue(enqueue(enqueue(s)));assert.equal(queuedCount(s),3);
  s=draft(s);assert.ok(!canSubmit(s));assert.equal(r(s,{type:'START'}),s);
  assert.equal(r(s,{type:'CANCEL_QUEUED',id:1}).turns.length,4);
  s=r(s,{type:'CANCEL_QUEUED',id:3});assert.deepEqual(s.turns.map(t=>t.id),[1,2,4]);
  s=r(s,{type:'START'});assert.deepEqual(s.turns.map(t=>t.id),[1,2,4,5]);
  assert.equal(begin(s,2),s); // Still one active HTTP slot.
  s=r(s,{type:'RESULT',id:1,response,at:300});assert.equal(begin(s,4),s);
  s=begin(s,2);assert.equal(s.turns.find(t=>t.id===2).status,'ANALYZING');
  assert.equal(r(s,{type:'RESET'}),s);
});
test('actual serial driver: repeated kick, deferred HTTP, automatic 1 -> 2 -> 3; max active=1',async()=>{
  let s=begin(enqueue(initialSession),1);s=r(s,{type:'RESULT',id:1,response,at:200});
  s=enqueue(enqueue(enqueue(s)));
  const q=new SerialQueue(),started=[],pending=[];let active=0,max=0;
  const next=()=>s.turns.find(t=>t.status==='QUEUED');
  const run=async t=>{
    s=begin(s,t.id);started.push(t.id);max=Math.max(max,++active);
    await new Promise(resolve=>pending.push(resolve));
    active--;s=r(s,{type:'RESULT',id:t.id,response,at:300});
  };
  const complete=q.kick(next,run);await q.kick(next,run);
  assert.deepEqual(started,[2]);pending.shift()();await tick();assert.deepEqual(started,[2,3]);
  pending.shift()();await tick();assert.deepEqual(started,[2,3,4]);
  pending.shift()();await complete;assert.equal(max,1);assert.equal(q.running,false);
});
test('settled operational error continues FIFO; unavailable/uncertain error pauses without losing draft',async()=>{
  for(const pause of [false,true]) {
    let s=enqueue(enqueue(initialSession));const q=new SerialQueue();const starts=[];
    await q.kick(()=>!s.queuePaused?s.turns.find(t=>t.status==='QUEUED'):undefined,async t=>{
      s=begin(s,t.id);starts.push(t.id);
      s=t.id===1?r(s,{type:'TURN_ERROR',id:t.id,message:'error',pause,uncertain:pause,at:200}):r(s,{type:'RESULT',id:t.id,response,at:200});
    });
    assert.deepEqual(starts,pause?[1]:[1,2]);
    if(pause) { assert.equal(r(s,{type:'RESET'}),s);assert.equal(queuedCount(s),1);
      s=r(s,{type:'RESUME_QUEUE'});assert.equal(begin(s,2).turns[1].status,'ANALYZING'); }
  }
});
test('recording cancellation preserves selected prompt, restores prior audio only when it existed',()=>{
  for(const prior of [null,audio]) {
    let s=prior?draft(initialSession):r(initialSession,{type:'PROMPT',prompt});
    s=r(s,{type:'PHASE',phase:'REQUESTING_MIC'});s=r(s,{type:'CAPTURE_STARTED'});
    s=r(s,{type:'CAPTURE_CANCELLED',audio:prior});assert.equal(s.prompt,prompt);assert.equal(s.audio,prior);
    assert.equal(s.phase,prior?'AUDIO_READY':'PROMPT_SELECTED');assert.equal(canSubmit(s),!!prior);
  }
});
test('quiet/normal/loud auto-fit stays readable and leaves raw PCM/WAV bytes identical; silence stays flat',()=>{
  for(const amplitude of [0.0001,0.2,0.95]) {
    const bytes=encodeWav(Float32Array.from({length:16000},(_,i)=>amplitude*Math.sin(i/11)),16000);
    const hash=b=>crypto.createHash('sha256').update(new Uint8Array(b)).digest('hex');
    const before=hash(bytes),parsed=parseWav(bytes),copy=parsed.samples.slice();
    const original=waveformPeaks(parsed.samples),display=autoFitPeaks(original);
    assert.ok(Math.abs(Math.max(...display)-0.84)<1e-10);
    assert.equal(hash(bytes),before);assert.deepEqual(parsed.samples,copy);
    assert.ok(Math.max(...original)<=amplitude+1/32768);
  }
  assert.deepEqual(autoFitPeaks([0,0,0]),[0,0,0]);
});
test('shipped worklet meters actual PCM and flags only very strong stereo cancellation, preserving arithmetic mean',()=>{
  let Processor;
  vm.runInNewContext(fs.readFileSync(new URL('../public/pcm-capture.js',import.meta.url),'utf8'),{
    AudioWorkletProcessor:class{messages=[];port={postMessage:m=>this.messages.push(m)}},sampleRate:8000,
    registerProcessor:(_,c)=>Processor=c,
  });
  for(const reverse of [false,true]) {
    const p=new Processor(),l=new Float32Array(800).fill(0.4),right=new Float32Array(800).fill(reverse?-0.4:0.4);
    for(let i=0;i<10;i++)p.process([[l,right]]);
    const d=p.stereoDiagnostic();assert.equal(d.suspectedCancellation,reverse);
    assert.ok(d.leftRms>0.39 && d.rightRms>0.39);
    const frames=p.messages.filter(m=>m.pcm);assert.ok(frames.every(m=>Math.abs(m.pcm[0]-(reverse?0:0.4))<1e-7));
    assert.ok(p.messages.some(m=>m.level));assert.equal(l[0],Math.fround(0.4));
  }
});
