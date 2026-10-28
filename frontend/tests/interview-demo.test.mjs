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
const { loadDemo, DEMOS, demoFromHash } = await import(compiled(path.join(root,'demo/loadDemo.ts')));
const { AnalysisStream } = await import(compiled(path.join(root,'workspace/AnalysisStream.tsx')));
const { segments } = await import(compiled(path.join(root,'prosody/curves.ts')));
const publicRoot = fileURLToPath(new URL('../public/',import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(publicRoot,'demo/manifest.json')));
const { engineeringWav } = await import('./support/engineeringWav.mjs');
const demoAudioAvailable = manifest.cases.every(c => fs.existsSync(path.join(publicRoot,'audio/reference',c.prompt_id+'.wav')));
const optionalAudioReason = 'Original Haruka WAVs are not distributed; this is not a DEMO acoustic validation.';
const get = async (url, init) => {
  assert.equal(init.method, undefined); assert.ok(init.signal instanceof AbortSignal);
  assert.ok(url.startsWith('/demo/') || url.startsWith('/audio/reference/'));
  const file = path.join(publicRoot,url.slice(1));
  // Deliberately non-matching engineering bytes exercise rejection/cancellation only.
  if (url.endsWith('.wav') && !fs.existsSync(file)) return new Response(engineeringWav());
  return new Response(fs.readFileSync(file));
};
for (const { prompt, label } of DEMOS) {
  test(`${label}: immutable MFA/pYIN receipts match exact synthetic WAV; four real sections`,{skip: !demoAudioAvailable && optionalAudioReason},async()=>{
    const d=await loadDemo(prompt.prompt_id,new AbortController().signal,get);
    const entry=manifest.cases.find(c=>c.prompt_id===prompt.prompt_id);
    assert.equal(d.response.audio.sha256,entry.audio_sha256);
    assert.equal(d.response.provenance.alignment_engine,'MFA_CPU_CLI');
    assert.equal(d.response.provenance.calibrated_diagnosis_ready,false);
    assert.equal(d.audio.samples.length,d.response.audio.sample_count);
    assert.equal(d.curves.learner.audio_sha256,d.response.audio.sha256);
    assert.deepEqual(d.curves.learner.frames,d.curves.reference.frames);
    assert.ok(d.curves.learner.frames.some(f=>f.f0_hz===null));
    assert.ok(segments(d.curves.learner,'hz').length>1);
    const turn={id:1,status:'COMPLETED',prompt:d.prompt,audio:{...d.audio,url:'blob:demo-test'},response:d.response};
    const html=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[turn],expanded:1,onToggle(){},playbackDisabled:false,onRetry(){},onCancelQueued(){},onCancelTurn(){},onSelection(){},demoCurves:d.curves}));
    for(const label of ['01 · 演示音频与语音波形','02 · 音高与语调','03 · 练习建议','04 · 实验 X-Ray','DEMO · Haruka 合成 WAV','已保存的 pYIN 提取结果','用这句重新练习']) assert.ok(html.includes(label),label);
    assert.ok(html.includes('class="experimental-details" open=""'));
    assert.ok(!html.includes('重新提取音高'));
    const live=renderToStaticMarkup(React.createElement(AnalysisStream,{turns:[turn],expanded:1,onToggle(){},playbackDisabled:false,onRetry(){},onCancelQueued(){},onCancelTurn(){},onSelection(){}}));
    assert.ok(!live.includes('class="experimental-details" open=""'));
    assert.ok(live.includes('查看音高与同句参考'));
  });
}
test('reject missing, corrupt and cross-sentence demo assets before displaying any results',async()=>{
  await assert.rejects(loadDemo('unknown',new AbortController().signal,get),/未找到/);
  await assert.rejects(loadDemo(DEMOS[0].prompt.prompt_id,new AbortController().signal,async()=>new Response('',{status:404})),/无法读取/);
  for(const suffix of ['.wav','-analysis.json','-prosody.json']) {
    const corrupt=async(url,init)=>url.endsWith(suffix)?new Response('wrong bytes'):get(url,init);
    await assert.rejects(loadDemo(DEMOS[0].prompt.prompt_id,new AbortController().signal,corrupt),/校验失败/);
  }
  const wrong=async(url,init)=>get(url.replaceAll('001','002'),init);
  await assert.rejects(loadDemo(DEMOS[0].prompt.prompt_id,new AbortController().signal,wrong),/校验失败/);
});
test('cancel while static files load: late successful responses cannot yield a demo',async()=>{
  const controller=new AbortController(); let resolve;
  const gate=new Promise(r=>resolve=r);
  const pending=loadDemo(DEMOS[0].prompt.prompt_id,controller.signal,async(url,init)=>{await gate;return get(url,init);});
  controller.abort(); resolve();
  await assert.rejects(pending,e=>e.name==='AbortError');
});
test('landing demo route admits only three known demos; ordinary practice remains ordinary',()=>{
  for(const {prompt} of DEMOS) assert.equal(demoFromHash(`#/workspace?demo=${prompt.prompt_id}`),prompt.prompt_id);
  for(const h of ['#/workspace','#top','#/workspace?demo=unknown','#/other?demo=learner-v1-001']) assert.equal(demoFromHash(h),null);
});
