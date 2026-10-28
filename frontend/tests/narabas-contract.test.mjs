import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const mod = async path => import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(
  fs.readFileSync(new URL('../src/'+path, import.meta.url), 'utf8'),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
const {validateContract} = await mod('api/validate.ts');
const {mapAnalysis,focusFor} = await mod('analysis/mapper.ts');
const {summarizeEvidence,guidanceFor} = await mod('analysis/guidance.ts');
const schema = JSON.parse(fs.readFileSync(new URL('../../data/contracts/api-v1-analysis.schema.json',import.meta.url)));
const fixture = JSON.parse(fs.readFileSync(new URL('../../data/examples/api-v1-narabas-analysis-response.json',import.meta.url)));

test('new schema accepts native pair provenance and rejects an unknown engine', () => {
  validateContract(fixture, schema, schema.$defs);
  const wrong = structuredClone(fixture);
  wrong.provenance.alignment_engine = 'UNLOCKED_FORK';
  assert.throws(() => validateContract(wrong, schema, schema.$defs));
});
test('native target keeps two phones and shared mora envelope with no fabricated realization advice', () => {
  const vm = mapAnalysis(fixture), target = fixture.targets[0];
  assert.equal(vm.targets[0].realization, '当前版本暂不提供实现候选比较。');
  const summary = summarizeEvidence(fixture, target);
  assert.deepEqual(summary.focus.phone, ['a','a']);
  assert.equal(summary.realization, null);
  assert.ok(guidanceFor(summary).every(g => g.source !== '/targets/0/realization'));
  const spans = target.mora_indices.map(i => focusFor(vm, 'mora', i).span);
  assert.deepEqual(spans[0], spans[1]);
  assert.deepEqual(spans[0], target.time_span);
});
