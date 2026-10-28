import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const read=p=>fs.readFileSync(new URL('../src/'+p,import.meta.url),'utf8');
const mod=async p=>import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(read(p),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
const {guidanceFor,summarizeEvidence}=await mod('analysis/guidance.ts');
const {SegmentPlayer,pauseOtherAudio}=await mod('audio/playback.ts');
const {sessionReducer:r,initialSession}=await mod('analysis/state.ts');
const fixture=JSON.parse(fs.readFileSync(new URL('../../data/examples/api-v1-analysis-response.json',import.meta.url),'utf8'));
function summary(direction='BELOW_REFERENCE_MEDIAN',variant='CANONICAL_SELECTED') {
  const response=structuredClone(fixture), t=response.targets[0];
  t.availability={duration:true,reference:true,deviation:true,realization:true,raw_f0:false,rms:false};
  t.deviation.direction=direction;t.realization.selected_variant=variant;t.realization.evidence_status='AVAILABLE';
  return summarizeEvidence(response,t);
}
for (const [direction,word] of [['BELOW_REFERENCE_MEDIAN','更完整'],['ABOVE_REFERENCE_MEDIAN','更紧凑'],['AT_REFERENCE_MEDIAN','保持稳定']]) {
  test('duration guidance '+direction+' is source-backed and non-diagnostic',()=>{
    const advice=guidanceFor(summary(direction));assert.match(advice[0].action,new RegExp(word));assert.equal(advice[0].source,'/targets/0/deviation/direction');
    assert.doesNotMatch(advice[0].action+advice[0].basis,/太短|太长|错误|标准|延长.*秒|缩短到/);
  });
}
for (const [variant,word] of [['CANONICAL_SELECTED','完整候选'],['REDUCED_SELECTED','简化候选']]) {
  test('realization guidance '+variant+' declares experimental limit',()=>{
    const advice=guidanceFor(summary(undefined,variant))[1];assert.match(advice.basis,new RegExp(word));assert.match(advice.basis,/不是正确 \/ 错误判断/);
  });
}
test('unavailable / partial / abstained channels cannot produce realization advice; independent duration survives',()=>{
  for (const status of ['PARTIAL','UNAVAILABLE','ABSTAINED']) { const s=summary();s.realization.evidence_status=status;assert.equal(guidanceFor(s).length,1); }
  const s=summary();s.availability.realization=false;s.availability.duration=false;assert.deepEqual(guidanceFor(s),[]);
  const ambiguous=summary(undefined,'AMBIGUOUS_OR_UNRESOLVED');assert.equal(guidanceFor(ambiguous).length,1);
  assert.doesNotMatch(JSON.stringify(guidanceFor(summary())),/音量过大|音高太高|重音不对|轻一点|重一点/);
});
test('EvidenceSummary excludes audio, RMS/F0, likelihood and raw transcript; pointers and interval are preserved',()=>{
  const s=summary();assert.equal(s.analysis_id,fixture.analysis_id);assert.deepEqual(s.focus.interval,fixture.targets[0].time_span);
  assert.deepEqual(Object.keys(s).sort(),['analysis_id','target','focus','duration','reference_relation','realization','availability','warnings','source_pointers'].sort());
  assert.ok(!('audio' in s));assert.ok(!('acoustics' in s));
});
function context() {
  const sources=[];
  return {sources,destination:{},resume:async()=>{},decodeAudioData:async()=>({duration:4}),createBufferSource(){const s={connect(){},disconnect(){s.disconnected=true},stop(){s.stopped=true},start(...args){s.args=args},onended:null};sources.push(s);return s;},close:async function(){this.closed=true}};
}
test('word and 30ms phone boundaries use exact audio clock offsets; end/stop/switch/reset release sources',async()=>{
  const previous=globalThis.document;globalThis.document={querySelectorAll:()=>[]};
  try {
    const c=context(),p=new SegmentPlayer(()=>c),blob=new Blob(['original']);let stopped=0;
    assert.equal(await p.play(blob,900,930,4000,()=>stopped++),true);
    assert.deepEqual(c.sources[0].args,[0,.9,.03]);c.sources[0].onended();assert.ok(c.sources[0].stopped);assert.equal(stopped,1);
    await p.play(blob,600,1700,4000,()=>stopped++);assert.deepEqual(c.sources[1].args,[0,.6,1.1]);
    const c2=context(),q=new SegmentPlayer(()=>c2);await q.play(blob,800,960,4000,()=>{});assert.ok(c.sources[1].stopped);
    pauseOtherAudio(undefined,true);assert.ok(c2.sources[0].stopped);q.dispose();p.dispose();assert.ok(c.closed && c2.closed);
  } finally {globalThis.document=previous;}
});
test('invalid intervals rejected without padding; cancelled pending decode never starts',async()=>{
  const previous=globalThis.document;globalThis.document={querySelectorAll:()=>[]};
  try {
    const c=context(),p=new SegmentPlayer(()=>c),blob=new Blob(['original']);
    for(const [a,b] of [[-1,30],[30,30],[50,30],[0,4001],[NaN,30]]) await assert.rejects(p.play(blob,a,b,4000,()=>{}));
    let resolve;c.decodeAudioData=()=>new Promise(r=>resolve=r);
    const pending=p.play(blob,900,930,4000,()=>{});await new Promise(r=>setImmediate(r));p.stop();resolve({});
    assert.equal(await pending,false);assert.equal(c.sources.length,0);p.dispose();
  } finally {globalThis.document=previous;}
});
test('late progress cannot mutate finished/queued turns or composer recording',()=>{
  const s={...initialSession,phase:'RECORDING',turns:[{id:1,status:'ANALYZING'},{id:2,status:'QUEUED'}]};
  const progress={stage_index:4,state:'RUNNING'};
  const n=r(s,{type:'PROGRESS',id:1,progress});assert.equal(n.phase,'RECORDING');assert.equal(n.turns[0].progress,progress);assert.equal(n.turns[1].progress,undefined);
  const done={...n,turns:[{...n.turns[0],status:'COMPLETED'}]};assert.equal(r(done,{type:'PROGRESS',id:1,progress:{stage_index:2}}).turns[0],done.turns[0]);
});
