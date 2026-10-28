import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import ts from 'typescript';
const source = path => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
async function module(path, transform = s => s) {
  const code = transform(ts.transpileModule(source(path), {compilerOptions:{target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext}}).outputText);
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
}
const {initialSession,sessionReducer:r,canSubmit,locked}=await module('analysis/state.ts');
const {elapsedLabel}=await module('workspace/elapsed.ts');
const {pauseOtherAudio}=await module('audio/playback.ts');
const {parseWav}=await module('audio/wav.ts');
const {mapAnalysis,warningText}=await module('analysis/mapper.ts');
const response=JSON.parse(fs.readFileSync(new URL('../../data/examples/api-v1-analysis-response.json',import.meta.url),'utf8'));
const prompt=response.prompt, audio={url:'blob:user',blob:new Blob(['input']),durationMs:3520};
const ready=()=>r(r(initialSession,{type:'PROMPT',prompt}),{type:'AUDIO',audio});
test('first submission keeps available composer, one queued turn; response expands same turn',()=>{
  let s=r(ready(),{type:'START'});
  assert.equal(s.composerOpen,true); assert.ok(!locked(s)); assert.equal(canSubmit(s),false);
  assert.equal(s.turns.length,1); assert.equal(s.expanded,null);
  s=r(s,{type:'REQUEST_STARTED',id:1,at:100});
  s=r(s,{type:'RESULT',id:1,response,at:3210});
  assert.equal(s.turns.length,1); assert.equal(s.turns[0].audio,audio);
  assert.equal(s.turns[0].requestEndedAt,3210);assert.equal(s.expanded,1);
  assert.ok(!locked(s)); assert.equal(s.composerOpen,true);assert.equal(s.audio,null);
});
test('same prompt retry needs new audio and appends next turn without replacing old result',()=>{
  let s=r(r(r(ready(),{type:'START'}),{type:'REQUEST_STARTED',id:1,at:100}),{type:'RESULT',id:1,response,at:2000});
  const old=s.turns[0];
  s=r(s,{type:'RETRY',prompt});assert.equal(s.prompt,prompt);assert.equal(s.audio,null);assert.ok(!canSubmit(s));
  s=r(r(s,{type:'AUDIO',audio:{...audio,url:'blob:new'}}),{type:'START'});
  assert.equal(s.turns.length,2);assert.equal(s.turns[0],old);assert.equal(s.turns[1].audio.url,'blob:new');
  s=r(r(s,{type:'REQUEST_STARTED',id:2,at:3000}),{type:'RESULT',id:2,response,at:4000});assert.equal(s.expanded,2);
  assert.equal(r(s,{type:'RESET'}),initialSession);
});
test('timer uses real monotonic elapsed; no start before request, no change after response/error, reset drops timer state',()=>{
  assert.equal(elapsedLabel(undefined,10000),'00:00');assert.equal(elapsedLabel(100,1100),'00:01');
  assert.equal(elapsedLabel(100,156100),'02:36');assert.equal(elapsedLabel(100,0),'00:00');
  for (const end of [{type:'RESULT',id:1,response,at:3100},{type:'TURN_ERROR',id:1,message:'连接中断',at:3100}]) {
    let s=r(r(ready(),{type:'START'}),{type:'REQUEST_STARTED',id:1,at:100});s=r(s,end);
    assert.equal(elapsedLabel(s.turns[0].requestStartedAt,s.turns[0].requestEndedAt),'00:03');
    assert.equal(r(s,{type:'REQUEST_STARTED',id:1,at:10000}),s);
    assert.equal(r(s,{type:'RESET'}).turns.length,0);
  }
});
test('error belongs to submitted turn and restores input, without silently claiming backend cancellation',()=>{
  const s=r(r(r(ready(),{type:'START'}),{type:'REQUEST_STARTED',id:1,at:100}),{type:'TURN_ERROR',id:1,message:'连接中断，无法确认本次分析结果',at:9000});
  assert.equal(s.error,null);assert.match(s.turns[0].error,/无法确认/);assert.ok(!locked(s));assert.ok(s.composerOpen);
});
test('playback mutex pauses references and user audio; capture/reset explicitly rewinds references only',()=>{
  const make=(reference)=>({dataset:{referenceReading:reference?'true':undefined},currentTime:2,paused:false,pause(){this.paused=true}});
  const a=make(true),b=make(true),user=make(false);
  const original=globalThis.document;
  globalThis.document={querySelectorAll:()=>[a,b,user]};
  try {
    pauseOtherAudio(b);assert.ok(a.paused);assert.ok(user.paused);assert.equal(b.paused,false);assert.equal(a.currentTime,2);
    pauseOtherAudio(user);assert.ok(b.paused);
    pauseOtherAudio(undefined,true);assert.equal(a.currentTime,0);assert.equal(b.currentTime,0);assert.equal(user.currentTime,2);
  } finally { globalThis.document=original; }
});
test('three static Japanese assets match approved prompt texts, PCM rate/format and provenance hashes', {skip: !['001','002','003'].every(id => fs.existsSync(new URL('../public/audio/reference/learner-v1-'+id+'.wav',import.meta.url))) && 'Original Haruka WAVs are not distributed; no acoustic validation claimed.'},()=>{
  const manifest=JSON.parse(fs.readFileSync(new URL('../public/audio/reference/manifest.json',import.meta.url),'utf8').replace(/^\uFEFF/,''));
  assert.equal(manifest.assets.length,3);
  const texts=['新しいスマートフォンを机に置きました。','来月、舞台でデビューします。','このシリーズを週末に見ます。'];
  for (const [i,a] of manifest.assets.entries()) {
    assert.equal(a.prompt_id,`learner-v1-00${i+1}`);assert.equal(a.text,texts[i]);assert.equal(a.type,'synthetic');assert.equal(a.locale,'ja-JP');
    const b=fs.readFileSync(new URL(`../public/${a.path}`,import.meta.url));
    assert.equal(crypto.createHash('sha256').update(b).digest('hex'),a.sha256);
    const decoded=parseWav(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));
    assert.equal(decoded.sampleRate,a.sample_rate);assert.ok(decoded.durationMs>1000);
    assert.ok(decoded.samples.some(x=>Math.abs(x)>0.01));
  }
});
test('humanized warning and realization preserve raw source and suspicious 30ms duration',()=>{
  const raw=structuredClone(response);raw.targets[0].duration.raw_duration_ms=30;raw.targets[0].realization.selected_variant='REDUCED_SELECTED';
  const mapped=mapAnalysis(raw);assert.equal(mapped.source,raw);assert.equal(mapped.targets[0].duration,'0.03 s');
  assert.equal(mapped.targets[0].realization,'当前实验探针更支持简化候选实现');
  assert.equal(warningText('CROSS_SENTENCE_CONTEXT_NOT_VALIDATED'),'目标词一致并不代表句子语境完全等价。');
});

test('no alignment stays abstained without fabricated duration, reference or timeline',()=>{
  const raw=structuredClone(response);raw.status='ABSTAINED';raw.timeline=null;
  const t=raw.targets[0];for(const k of Object.keys(t.availability)) t.availability[k]=false;
  for(const k of ['time_span','duration','reference','deviation','realization','acoustics']) t[k]=null;
  t.evidence_status='ABSTAINED';t.reasons=[{stage:'ALIGNED',reason_code:'ALIGNMENT_UNUSABLE',message:'Declared target evidence is unavailable.'}];
  let s=r(r(ready(),{type:'START'}),{type:'REQUEST_STARTED',id:1,at:100});
  s=r(s,{type:'RESULT',id:1,response:raw,at:9000});
  assert.equal(s.turns[0].status,'ABSTAINED');assert.equal(s.turns[0].audio,audio);assert.equal(s.turns[0].error,undefined);
  const vm=mapAnalysis(raw);assert.equal(vm.timeline,null);assert.match(vm.targets[0].duration,/不可用/);assert.match(vm.status,/无法/);
  assert.match(warningText('ALIGNMENT_UNUSABLE'),/可靠对齐/);
});
test('analysis request invokes start immediately before fetch and still sends only prompt_id + uploaded audio',async()=>{
  const validateCode=ts.transpileModule(source('api/validate.ts'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
  const validateUrl=`data:text/javascript;base64,${Buffer.from(validateCode).toString('base64')}`;
  const schema=JSON.parse(fs.readFileSync(new URL('../../data/contracts/api-v1-analysis.schema.json',import.meta.url),'utf8'));
  const client=await module('api/client.ts',s=>s.replace(/import schema from [^;]+;/,`const schema=${JSON.stringify(schema)};`).replace('"./validate"',JSON.stringify(validateUrl)).replace('import.meta.env.VITE_API_BASE_URL','""'));
  const original=globalThis.fetch,events=[];
  globalThis.fetch=async(url,options)=>{
    events.push('fetch');assert.equal(url,'/api/v1/analyses');assert.equal(options.method,'POST');
    assert.deepEqual([...options.body.keys()],['prompt_id','audio']);assert.equal(options.body.get('prompt_id'),prompt.prompt_id);
    assert.equal(await options.body.get('audio').text(),'input');return {ok:true,json:async()=>response};
  };
  try { await client.analyze(prompt.prompt_id,audio.blob,()=>events.push('start')); assert.deepEqual(events,['start','fetch']); }
  finally { globalThis.fetch=original; }
});

test('cancel stays active until backend confirmation; a late cancellation cannot erase a completed result or next draft',()=>{
  let s=r(r(ready(),{type:'START'}),{type:'REQUEST_STARTED',id:1,at:100});
  s=r(s,{type:'PROMPT',prompt});s=r(s,{type:'AUDIO',audio});
  s=r(s,{type:'CANCEL_REQUESTED',id:1});
  assert.equal(s.turns[0].status,'ANALYZING');assert.equal(s.turns[0].cancelRequested,true);
  assert.equal(r(s,{type:'RESET'}),s);
  s=r(s,{type:'CANCEL_FAILED',id:1,message:'无法确认'});
  assert.equal(s.turns[0].status,'ANALYZING');assert.equal(s.turns[0].cancelRequested,false);
  const cancelled=r(s,{type:'CANCEL_CONFIRMED',id:1,at:1200});
  assert.equal(cancelled.turns[0].status,'CANCELLED');assert.equal(cancelled.phase,'AUDIO_READY');assert.equal(cancelled.audio,audio);
  assert.equal(cancelled.turns[0].response,undefined);
  const finished=r(s,{type:'RESULT',id:1,response,at:1000});
  assert.equal(r(finished,{type:'CANCEL_CONFIRMED',id:1,at:1100}).turns[0].status,response.status);
});

test('private cancellation token is a header, keeps upload fields unchanged and targets only that request',async()=>{
  const validateCode=ts.transpileModule(source('api/validate.ts'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
  const validateUrl=`data:text/javascript;base64,${Buffer.from(validateCode).toString('base64')}`;
  const schema=JSON.parse(fs.readFileSync(new URL('../../data/contracts/api-v1-analysis.schema.json',import.meta.url),'utf8'));
  const client=await module('api/client.ts',s=>s.replace(/import schema from [^;]+;/,`const schema=${JSON.stringify(schema)};`).replace('"./validate"',JSON.stringify(validateUrl)).replace('import.meta.env.VITE_API_BASE_URL','""'));
  const token='bc17a8a4-ce2a-45c4-b157-a61c06a5f488',original=globalThis.fetch,controller=new AbortController();
  let calls=0;
  globalThis.fetch=async(url,options)=>{
    calls++;assert.equal(options.method,'POST');
    if(calls===1){assert.equal(options.headers['X-Analysis-Token'],token);assert.equal(options.signal,controller.signal);assert.deepEqual([...options.body.keys()],['prompt_id','audio']);return {ok:true,json:async()=>response};}
    assert.equal(url,`/api/v1/analyses/cancel/${token}`);return {ok:true,json:async()=>({status:'CANCELLED'})};
  };
  try {await client.analyze(prompt.prompt_id,audio.blob,undefined,token,controller.signal);assert.equal((await client.cancelAnalysis(token)).status,'CANCELLED');assert.equal(calls,2);}
  finally{globalThis.fetch=original;}
});
