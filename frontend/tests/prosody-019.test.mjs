import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const require = createRequire(import.meta.url), modules = new Map();
function compiled(file) {
  file = path.resolve(file); if (modules.has(file)) return modules.get(file);
  const code = ts.transpileModule(fs.readFileSync(file,'utf8'), { compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText
    .replace(/import "[^\"]+\.css";/g,'').replace(/from "([^"]+)"/g,(all,name)=>{
      if (!name.startsWith('.')) return `from "${pathToFileURL(require.resolve(name)).href}"`;
      let target=path.resolve(path.dirname(file),name); if(!fs.existsSync(target)) target+=fs.existsSync(target+'.ts')?'.ts':'.tsx';
      return `from "${compiled(target)}"`;
    });
  const url='data:text/javascript;base64,'+Buffer.from(code).toString('base64'); modules.set(file,url); return url;
}
const root=fileURLToPath(new URL('../src/prosody/',import.meta.url));
const { validateCurves, segments, pitchValue, pitchDomain, pitchEvidenceNote }=await import(compiled(path.join(root,'curves.ts')));
const { extractCurves, cachedCurves }=await import(compiled(path.join(root,'client.ts')));
const { ProsodyPanel }=await import(compiled(path.join(root,'ProsodyPanel.tsx')));
const prompt='learner-v1-001';
const hash='a'.repeat(64), referenceHash='b'.repeat(64);
const frame=(t,hz,p=.9)=>({time_ms:t,f0_hz:hz,voiced:hz!==null,pyin_voiced:hz!==null,voiced_probability:p,rms_dbfs:hz===null?-120:-12});
function track(sha=hash) {return {status:'AVAILABLE',reason:null,audio_sha256:sha,duration_ms:1000,sample_rate_hz:16000,sample_count:16000,parameters:{hop_ms:20,frame_length:2048},extraction_ms:20,
  frames:[frame(0,220),frame(20,230),frame(40,null),frame(60,240),frame(80,440,.2),frame(100,220)],
  observations:{median_f0_hz:220,p10_f0_hz:220,p90_f0_hz:440,voiced_fraction:.8,median_voiced_probability:.9,late_minus_early_semitones:null}};}
function curves(sha=hash) {return {schema_version:'prosody-1.0',algorithm:'prosody-pyin-1',prompt_id:prompt,learner:track(sha),reference:track(referenceHash),reference_reason:null,total_ms:50,
  reference_source:{prompt_id:prompt,type:'synthetic',voice:'Microsoft Haruka Desktop',engine:'Windows SAPI / System.Speech',text:'新しいスマートフォンを机に置きました。',sha256:referenceHash,path:'audio/reference/learner-v1-001.wav',label:'合成参考，非母语者准确性标准'}};}

test('unvoiced frames split the path and weak evidence is kept distinct',()=>{
  const t=track(), s=segments(t,'hz');
  assert.deepEqual(s.map(s=>s.points.map(p=>p.time)),[[0,20],[60],[80],[100]]);
  assert.deepEqual(s.map(s=>s.weak),[false,false,true,false]);
  assert.equal(pitchValue(t.frames[2],t,'hz'),null);
  assert.deepEqual(t.frames.map(f=>f.f0_hz),[220,230,null,240,440,220]);
});
test('TASK020 sparse evidence note uses existing admitted frames without changing points or gates',()=>{
  const t=track(), before=JSON.stringify(t), paths=segments(t,'hz');
  assert.match(pitchEvidenceNote(t),/5 \/ 6 帧/);
  assert.match(pitchEvidenceNote(t),/不足以比较首尾走势/);
  assert.equal(JSON.stringify(t),before);assert.deepEqual(segments(t,'hz'),paths);
  t.observations.late_minus_early_semitones=1;
  assert.match(pitchEvidenceNote(t),/空白不直接表示停顿或发音错误/);
  t.status='ABSTAINED';t.reason='INSUFFICIENT_VOICED_FRAMES';
  assert.match(pitchEvidenceNote(t),/只提取到少量有效音高片段/);
  assert.match(pitchEvidenceNote(t),/手动练习/);
});
test('semitone baseline is explicit, per-track and never changes actual F0',()=>{
  const t=track(), before=JSON.stringify(t);
  assert.equal(pitchValue(t.frames[0],t,'semitones'),0);
  assert.equal(pitchValue(t.frames[4],t,'semitones'),12);
  const other=track();other.observations.median_f0_hz=440;
  assert.equal(pitchValue(other.frames[4],other,'semitones'),0);
  assert.deepEqual(pitchDomain([t,other],'semitones'),[-13,13]);assert.equal(JSON.stringify(t),before);
});
test('invalid, stale, wrong audio and wrong-reference responses cannot draw curves',()=>{
  assert.equal(validateCurves(curves(),prompt,hash).learner.audio_sha256,hash);
  for(const change of [r=>r.prompt_id='learner-v1-002',r=>r.learner.audio_sha256='c'.repeat(64),r=>r.reference_source.sha256=hash,
    r=>r.learner.frames[0].f0_hz=Infinity,r=>r.learner.frames[1].time_ms=-1,r=>r.learner.frames[2].f0_hz=220,
    r=>r.learner.frames[0].voiced_probability=2,r=>r.learner.observations.median_f0_hz=0,r=>r.learner.frames[0].time_ms=1000,
    r=>r.learner.frames=[],r=>r.algorithm='unapproved',r=>r.reference_source.voice='unknown',r=>r.learner.sample_count=1]) {
    const r=curves();change(r);assert.throws(()=>validateCurves(r,prompt,hash));
  }
});
test('abstention never produces a path; independent reference may still be available',()=>{
  const r=curves();r.learner.status='ABSTAINED';r.learner.reason='F0_EXTRACTION_FAILED';r.learner.observations=null;r.learner.frames=r.learner.frames.map(f=>({...f,f0_hz:null,voiced:false}));
  assert.equal(validateCurves(r,prompt,hash).learner.status,'ABSTAINED');assert.deepEqual(segments(r.learner,'hz'),[]);
  assert.ok(segments(r.reference,'hz').length);
});
test('client binds results and cache to WAV bytes; abort discards late results, re-record is isolated',async()=>{
  const oldFetch=globalThis.fetch;
  try {
    const blob=new Blob(['engineering-fixture']), digest=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
    const sha=Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
    globalThis.fetch=async()=>({ok:true,json:async()=>curves(sha)});
    const result=await extractCurves(blob,prompt,new AbortController().signal);
    assert.equal(cachedCurves(blob,prompt),result);assert.equal(cachedCurves(new Blob(['engineering-fixture']),prompt),null);
    assert.equal(cachedCurves(blob,'learner-v1-002'),null);
    const another=new Blob(['engineering-fixture']), cancel=new AbortController();
    globalThis.fetch=async()=>({ok:true,json:async()=>{cancel.abort();return curves(sha);}});
    await assert.rejects(extractCurves(another,prompt,cancel.signal),{name:'AbortError'});assert.equal(cachedCurves(another,prompt),null);
    const controller=new AbortController();controller.abort();let sent=false;globalThis.fetch=async()=>{sent=true;};
    await assert.rejects(extractCurves(blob,prompt,controller.signal));assert.equal(sent,false);
  } finally {globalThis.fetch=oldFetch;}
});
test('React cold panel requires explicit local extraction and leaves existing WAV unchanged',()=>{
  const audio={blob:new Blob(['test']),name:'test.wav',durationMs:1000,sampleRate:16000,samples:new Float32Array(16000),url:'blob:test'};
  const html=renderToStaticMarkup(React.createElement(ProsodyPanel,{audio,promptId:prompt,disabled:false}));
  assert.match(html,/查看音高与同句参考/);assert.match(html,/无需等待自动对齐/);assert.match(html,/点击后仅发送到本地服务/);assert.doesNotMatch(html,/<svg/);
  const noPrompt=renderToStaticMarkup(React.createElement(ProsodyPanel,{audio,disabled:false}));assert.match(noPrompt,/先选择本次朗读/);assert.match(noPrompt,/disabled/);
});
test('busy and network failures abstain without caching a failed request',async()=>{
  const oldFetch=globalThis.fetch, blob=new Blob(['test']);
  try {globalThis.fetch=async()=>({ok:false,status:503});await assert.rejects(extractCurves(blob,prompt,new AbortController().signal),/忙碌/);
    globalThis.fetch=async()=>{throw new Error('network');};await assert.rejects(extractCurves(blob,prompt,new AbortController().signal),/network/);assert.equal(cachedCurves(blob,prompt),null);
  } finally {globalThis.fetch=oldFetch;}
});
