import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const require = createRequire(import.meta.url), cache = new Map();
const root = fileURLToPath(new URL('../src/', import.meta.url));
// Execute the real TS/TSX modules, including React output; not source-string snapshots.
function compiled(file) {
  file = path.resolve(file);
  if (cache.has(file)) return cache.get(file);
  if (file.endsWith('.json')) return 'data:text/javascript;base64,' + Buffer.from('export default '+fs.readFileSync(file,'utf8')).toString('base64');
  const code = ts.transpileModule(fs.readFileSync(file,'utf8'), { compilerOptions:{ target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX } }).outputText
    .replace(/import "[^\"]+\.css";/g,'')
    .replace(/from "([^"]+)"/g,(all,name)=>{
      if (!name.startsWith('.')) return `from "${pathToFileURL(require.resolve(name)).href}"`;
      let target = path.resolve(path.dirname(file),name);
      if (!fs.existsSync(target)) target += fs.existsSync(target+'.ts') ? '.ts' : '.tsx';
      return `from "${compiled(target)}"`;
    }).replaceAll('import.meta.env.BASE_URL',"'/'").replaceAll('import.meta.env.DEV','false');
  const url = 'data:text/javascript;base64,'+Buffer.from(code).toString('base64'); cache.set(file,url);return url;
}
const mod = async name => import(compiled(path.join(root,name)));
const { candidatesFor, validSpan, turnEvidenceState, inputEvidenceState, MVP_PROMPTS, TARGETS, analysisError } = await mod('analysis/mvp.ts');
const { emptySelection, updateSelection, selectionStatus, selectionFrom, timeAt } = await mod('audio/selection.ts');
const { initialSession, sessionReducer:r } = await mod('analysis/state.ts');
const { SegmentPlayer } = await mod('audio/playback.ts');
const { parseWav } = await mod('audio/wav.ts');
const { AudioInspector } = await mod('workspace/AudioInspector.tsx');
const { AnalysisStream } = await mod('workspace/AnalysisStream.tsx');
const { ReferenceReading } = await mod('workspace/ReferenceReading.tsx');
const fixture = JSON.parse(fs.readFileSync(new URL('../../data/examples/api-v1-analysis-response.json',import.meta.url)));
const frozen = JSON.parse(fs.readFileSync(new URL('../../data/prompts/learner-pilot-v1.json',import.meta.url)));
// Structural tests use an authored tone, independent of optional speech assets.
const { engineeringWav } = await import('./support/engineeringWav.mjs');
const buffer = engineeringWav(fixture.audio.duration_ms);
const bytes = buffer.buffer.slice(buffer.byteOffset,buffer.byteOffset+buffer.byteLength);
const asset = {...parseWav(bytes),blob:new Blob([bytes]),url:'blob:engineering-synthetic',name:'synthetic.wav'};
const aligned = () => { const f=structuredClone(fixture);f.audio.duration_ms=asset.durationMs;return f; };
test('exact three frozen prompt texts, lexical targets and vowel labels; no extra prompts',()=>{
  assert.equal(MVP_PROMPTS.length,3);
  for(const [i,p] of MVP_PROMPTS.entries()) {assert.equal(p.prompt_id,frozen.prompts[i].prompt_id);assert.equal(p.display_text,frozen.prompts[i].text);assert.equal(p.prompt_version,String(frozen.prompt_pack_version));assert.equal(TARGETS[p.prompt_id].word,frozen.prompts[i].targets[0].surface_hint);}
  assert.deepEqual(MVP_PROMPTS.map(p=>TARGETS[p.prompt_id].vowel),['マー /aː/','ビュー /uː/','リー /iː/']);
});
test('candidate source preserves MFA time values; missing/invalid/foreign results abstain',()=>{
  const f=aligned(), before=JSON.stringify(f), c=candidatesFor(f,f.prompt.prompt_id,asset.durationMs);
  const w=f.timeline.words.find(w=>w.index===f.targets[0].word_index);
  assert.deepEqual(c.word,{start_ms:w.start_ms,end_ms:w.end_ms});assert.deepEqual(c.vowel,f.targets[0].time_span);assert.equal(c.structureAvailable,true);assert.equal(JSON.stringify(f),before);
  for(const mutate of [f=>f.timeline=null,f=>f.timeline.phones=[],f=>f.targets=[],f=>f.prompt.prompt_id='unknown',f=>f.audio.duration_ms+=1000,f=>f.provenance.alignment_engine='NARABAS_CPU_WORKER',f=>f.timeline.words[0].end_ms=99999,f=>f.status='ABSTAINED']) {const bad=aligned();mutate(bad);const result=candidatesFor(bad,'learner-v1-001',asset.durationMs);assert.equal(result.word,null);assert.equal(result.vowel,null);assert.equal(result.structureAvailable,false);}
});
test('bad vowel and shared mora timing never enables experimental structure/playback',()=>{
  for(const s of [{start_ms:-1,end_ms:200},{start_ms:200,end_ms:200},{start_ms:0,end_ms:1},{start_ms:0,end_ms:99999}]) {const f=aligned();f.targets[0].time_span=s;const c=candidatesFor(f,'learner-v1-001',asset.durationMs);assert.equal(c.vowel,null);assert.equal(c.structureAvailable,false);}
  const f=aligned();f.timeline.morae[0].shared_span={start_ms:0,end_ms:99999};assert.equal(candidatesFor(f,'learner-v1-001',asset.durationMs).structureAvailable,false);
});
test('word confirmation never creates vowel validation; word edits revoke confirmation',()=>{
  const word=updateSelection(emptySelection,'word',{start_ms:700,end_ms:1400});
  const confirmed={...word,wordConfirmed:true};assert.deepEqual(selectionStatus(confirmed),['WORD_REGION_USER_CONFIRMED']);
  const vowel=updateSelection(confirmed,'vowel',{start_ms:900,end_ms:1060});assert.deepEqual(selectionStatus(vowel),['WORD_REGION_USER_CONFIRMED','VOWEL_REGION_USER_SELECTED']);
  const adjusted=updateSelection(vowel,'word',{start_ms:650,end_ms:1400});assert.equal(adjusted.wordConfirmed,false);assert.deepEqual(selectionStatus(adjusted),['VOWEL_REGION_USER_SELECTED']);assert.ok(!selectionStatus(vowel).includes('VOWEL_BOUNDARY_VALIDATED'));assert.equal(confirmed.vowel,null);
});
test('coordinates and drag intervals clamp only UI positions, reject empty or invalid spans',()=>{
  assert.equal(timeAt(300,600,4000),2000);assert.equal(timeAt(-20,600,4000),0);assert.equal(timeAt(700,600,4000),4000);
  assert.deepEqual(selectionFrom(1400,700,4000),{start_ms:700,end_ms:1400});assert.throws(()=>selectionFrom(0,0,4000));assert.throws(()=>selectionFrom(NaN,10,4000));
  for(const s of [{start_ms:-1,end_ms:20},{start_ms:20,end_ms:10},{start_ms:0,end_ms:4001},{start_ms:NaN,end_ms:30}]) assert.equal(validSpan(s,4000),false);
});
test('selection persists from draft to submitted/failed/cancelled Turn; no change to WAV or response',()=>{
  let s=r(r(initialSession,{type:'PROMPT',prompt:MVP_PROMPTS[0]}),{type:'AUDIO',audio:asset});
  const selection={word:{start_ms:700,end_ms:1400},vowel:null,wordConfirmed:true};s=r(s,{type:'SELECTION',selection});s=r(s,{type:'START'});s=r(s,{type:'REQUEST_STARTED',id:1,at:0});
  assert.deepEqual(s.turns[0].audio.selection,selection);assert.equal(s.turns[0].audio.blob,asset.blob);assert.equal(s.turns[0].audio.samples,asset.samples);
  s=r(s,{type:'CANCEL_CONFIRMED',id:1,at:10});s=r(s,{type:'RESULT',id:1,response:aligned(),at:12});assert.equal(s.turns[0].status,'CANCELLED');assert.equal(s.turns[0].response,undefined);assert.deepEqual(s.turns[0].audio.selection,selection);
  const other=r(s,{type:'SELECTION',turnId:1,selection:{...selection,wordConfirmed:false}});assert.equal(other.turns[0].audio.selection.wordConfirmed,false);assert.equal(other.audio,null);
});
test('actual front-end state mapping distinguishes unavailable, errors, candidates and independent input',()=>{
  const t={id:1,audio:asset,prompt:MVP_PROMPTS[0],status:'COMPLETED',response:aligned()};assert.equal(turnEvidenceState(t),'EXPERIMENTAL_BOUNDARY');
  assert.equal(turnEvidenceState({...t,status:'ERROR',errorCode:'NETWORK_ERROR'}),'ANALYSIS_UNAVAILABLE');assert.equal(turnEvidenceState({...t,status:'ERROR',errorCode:'INTERNAL_PIPELINE_ERROR'}),'ANALYSIS_FAILED');
  assert.equal(turnEvidenceState({...t,status:'ERROR',errorCode:'HTTP_ERROR'}),'ANALYSIS_UNAVAILABLE');
  assert.equal(turnEvidenceState({...t,status:'CANCELLED'}),'ANALYSIS_UNAVAILABLE');assert.equal(turnEvidenceState({...t,status:'ANALYZING'}),'ANALYZING');assert.equal(turnEvidenceState({...t,response:undefined}),'USER_SELECTION_AVAILABLE');
  assert.equal(inputEvidenceState('RECORDING',false),'RECORDING');assert.equal(inputEvidenceState('AUDIO_READY',true),'AUDIO_READY');assert.equal(inputEvidenceState('IDLE',false),'INPUT_READY');assert.match(analysisError('ALIGNMENT_RUNTIME_UNAVAILABLE'),/自动对齐服务当前不可用/);
});
test('changing the draft prompt revokes target-specific selection without changing the original WAV',()=>{
  const selection={word:{start_ms:700,end_ms:1400},vowel:{start_ms:900,end_ms:1060},wordConfirmed:true};
  const s={...initialSession,prompt:MVP_PROMPTS[0],phase:'AUDIO_READY',audio:{...asset,selection}};
  assert.equal(r(s,{type:'PROMPT',prompt:MVP_PROMPTS[0]}).audio.selection,selection);
  const changed=r(s,{type:'PROMPT',prompt:MVP_PROMPTS[1]});
  assert.equal(changed.audio.selection,undefined);assert.equal(changed.audio.blob,asset.blob);assert.equal(changed.audio.samples,asset.samples);assert.equal(changed.phase,'AUDIO_READY');
  assert.deepEqual(s.audio.selection,selection);
});
test('React renders a real wave and manual controls without any analysis response',()=>{
  const html=renderToStaticMarkup(React.createElement(AudioInspector,{audio:asset,promptId:'learner-v1-001',disabled:false,onChange:()=>{}}));
  assert.match(html,/data-real-waveform="true"/);assert.match(html,/循环试听选区/);assert.match(html,/原始 WAV 时间轴/);assert.match(html,/マー \/aː\//);assert.doesNotMatch(html,/VOWEL_BOUNDARY_VALIDATED|准确率|发音得分/);
});
test('React completed view hides personal diagnosis and labels every research area experimental',()=>{
  const turn={id:1,audio:asset,prompt:MVP_PROMPTS[0],status:'COMPLETED',response:aligned()};
  const html=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[turn],expanded:1,onToggle:()=>{},playbackDisabled:false,onRetry:()=>{},onCancelQueued:()=>{},onCancelTurn:()=>{},onSelection:()=>{}}));
  assert.match(html,/自动边界仍处于实验验证阶段/);assert.match(html,/实验 X-Ray 结构与研究数据（未经边界验证）/);assert.match(html,/候选区间时长不等于/);assert.doesNotMatch(html,/把目标长音保持得更完整|更紧凑|练习重点|发音准确率|已达到母语者标准/);
  const bad=aligned();bad.timeline.phones[0].end_ms=99999;const hidden=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[{...turn,response:bad}],expanded:1,onToggle:()=>{},playbackDisabled:false,onRetry:()=>{},onCancelQueued:()=>{},onCancelTurn:()=>{},onSelection:()=>{}}));assert.doesNotMatch(hidden,/实验 X-Ray 结构与研究数据/);assert.match(hidden,/未展示不合法的自动结构/);
});
test('React backend error/cancellation retain original audio and manual selection tools',()=>{
  for(const status of ['ERROR','CANCELLED']) {const html=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[{id:1,audio:asset,prompt:MVP_PROMPTS[0],status,error:status==='ERROR'?analysisError('NETWORK_ERROR'):undefined}],expanded:null,onToggle:()=>{},playbackDisabled:false,onRetry:()=>{},onCancelQueued:()=>{},onCancelTurn:()=>{},onSelection:()=>{}}));assert.match(html,/原音波形与区域选择/);assert.match(html,/循环试听选区/);assert.match(html,/重新录音/);}
});
test('native reading metadata is original other-context text; missing reference degrades explicitly',()=>{
  for(const p of MVP_PROMPTS) {const html=renderToStaticMarkup(React.createElement(ReferenceReading,{promptId:p.prompt_id,disabled:false}));assert.match(html,/合成朗读辅助，不是母语者实录/);assert.ok(html.includes(TARGETS[p.prompt_id].sentence));assert.match(html,/未提供原生参考音频读取/);assert.match(html,/不代表严格等价/);}
  const missing=renderToStaticMarkup(React.createElement(ReferenceReading,{promptId:'missing',disabled:false}));assert.match(missing,/朗读音频待准备/);assert.match(missing,/disabled/);
});
test('loop uses exact original offset/loop boundaries and stops across players and dispose',async()=>{
  const old=globalThis.document;globalThis.document={querySelectorAll:()=>[]};
  const sources=[];const context={destination:{},resume:async()=>{},decodeAudioData:async()=>({duration:4}),createBufferSource:()=>{const s={connect(){},disconnect(){s.disconnected=true},stop(){s.stopped=true},start(...args){s.args=args}};sources.push(s);return s;},close:async()=>{context.closed=true}};
  const p=new SegmentPlayer(()=>context),q=new SegmentPlayer(()=>context),blob=new Blob(['test']);
  try {await p.play(blob,700,1400,4000,()=>{},true);assert.deepEqual(sources[0].args,[0,.7]);assert.equal(sources[0].loop,true);assert.equal(sources[0].loopStart,.7);assert.equal(sources[0].loopEnd,1.4);await q.play(blob,900,1060,4000,()=>{});assert.equal(sources[0].stopped,true);assert.deepEqual(sources[1].args,[0,.9,.16]);p.dispose();q.dispose();assert.equal(sources[1].stopped,true);assert.equal(context.closed,true);}
  finally {globalThis.document=old;}
});
test('playback rejects decoded time-axis mismatch and emits no source',async()=>{
  const old=globalThis.document;globalThis.document={querySelectorAll:()=>[]};let created=0;
  const p=new SegmentPlayer(()=>({resume:async()=>{},decodeAudioData:async()=>({duration:2}),createBufferSource:()=>{created++},close:async()=>{}}));
  try {await assert.rejects(p.play(new Blob(['x']),700,1400,4000,()=>{}),/原始 WAV 不一致/);assert.equal(created,0);p.dispose();}finally {globalThis.document=old;}
});

test('TASK020 practice controls precede closed precision tools and respect safe disabled states',()=>{
  const props={audio:asset,promptId:'learner-v1-001',disabled:false,onChange:()=>{},onRerecord:()=>{}};
  const html=renderToStaticMarkup(React.createElement(AudioInspector,props));
  assert.ok(html.indexOf('原音与选区试听') < html.indexOf('精确调整 · 时间与缩放'));
  assert.ok(html.indexOf('02 · 音高与语调') < html.indexOf('03 · 练习建议'));
  assert.match(html,/<details class="selection-secondary">/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>循环试听选区<\/button>/);
  assert.match(html,/<button[^>]*>再次录音<\/button>/);
  const selected={...asset,selection:{word:{start_ms:700,end_ms:1400},vowel:null,wordConfirmed:false}};
  const ready=renderToStaticMarkup(React.createElement(AudioInspector,{...props,audio:selected}));
  assert.doesNotMatch(ready,/<button[^>]*disabled=""[^>]*>循环试听选区<\/button>/);
  const blocked=renderToStaticMarkup(React.createElement(AudioInspector,{...props,audio:selected,disabled:true}));
  for(const label of ['试听整段原音','循环试听选区','再次录音']) assert.match(blocked,new RegExp(`<button[^>]*disabled=""[^>]*>${label}</button>`));
});
test('TASK020 experimental candidates, timestamps and statistics remain inside closed disclosures',()=>{
  const response=aligned(), before=JSON.stringify(response);
  const html=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[{id:1,audio:asset,prompt:MVP_PROMPTS[0],status:'COMPLETED',response}],expanded:1,onToggle:()=>{},playbackDisabled:false,onRetry:()=>{},onCancelQueued:()=>{},onCancelTurn:()=>{},onSelection:()=>{}}));
  assert.match(html,/<details class="candidate-notice"[^>]*><summary>实验 X-Ray/);
  assert.match(html,/<details class="experimental-details"><summary>04 · 实验 X-Ray · 技术证据<\/summary>/);
  assert.doesNotMatch(html,/<details[^>]*open=""/);
  assert.ok(html.indexOf('参考中位数') > html.indexOf('04 · 实验 X-Ray · 技术证据'));
  assert.ok(html.indexOf('Phone · 原生标签') > html.indexOf('04 · 实验 X-Ray · 技术证据'));
  assert.match(html,/目标词 \/ 冻结目标音/);assert.match(html,/候选区间原生标签/);
  assert.ok(html.includes('マー /aː/'));
  const phone=response.timeline.phones.find(p=>p.word_index===response.targets[0].word_index);
  assert.ok(html.includes(`>${phone.symbol}</button>`));
  assert.equal(JSON.stringify(response),before);
});
