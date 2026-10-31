const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/run-labels.js'), 'utf8');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../annotations/run-labels.json'), 'utf8'));
function setup(fetch) {
  const window = {};
  vm.runInNewContext(source, {window, fetch, document:{}});
  return window.yamRunLabels;
}
test('published export is complete, scoped and contains no raw identities or provider billing metadata', async () => {
  const api = setup(async () => ({ok:true, json:async () => data}));
  await api.load();
  assert.equal(data.runs.length, 416);
  assert.equal(new Set(data.runs.map(r => r.episode_id)).size, 416);
  assert.equal(data.runs.filter(r => r.human_review).length, 10);
  const counts = {};
  for (const run of data.runs) counts[api.outcome(run, 'auto')] = (counts[api.outcome(run, 'auto')] || 0) + 1;
  assert.deepEqual(counts, {Failure:259, Success:125, Uncertain:32});
  for (const run of data.runs) assert.deepEqual(Object.keys(run).sort(), ['auto_assessment','episode_id','human_review','robot_id']);
  const run = data.runs[0];
  assert.equal(api.outcome({...run, robot_id:'another-robot'}, 'auto'), 'Unscored');
  assert.equal(api.outcome({episode_id:'ep_future', robot_id:run.robot_id}, 'auto'), 'Unscored');
});
test('model predictions never override runner eligibility, actual reviews or community consensus', async () => {
  const api = setup(async () => ({ok:true, json:async () => data}));
  await api.load();
  const run = data.runs.find(r => r.auto_assessment.label === 'Failure');
  const human = {...run, assessment:{label:'Success', eligibility:'included'}};
  assert.equal(api.outcome(human, 'auto'), 'Failure');
  assert.equal(api.outcome(human, 'human'), 'Success');
  assert.equal(human.assessment.label, 'Success');
  assert.equal(api.outcome({...human, assessment:{label:'Success',eligibility:'excluded'}}, 'human'), 'Unscored');
  assert.equal(api.outcome({...run, assessment:{ended:false}}, 'human'), 'Unscored');
  assert.equal(api.outcome({assessment:{community:{label:'Failure'}}}, 'human'), 'Failure');
  const uncertain = data.runs.find(r => r.human_review?.label === 'Uncertain');
  assert.equal(api.outcome(uncertain, 'human'), 'Uncertain');
  assert.match(api.summary(data.runs, 'auto'), /416 of 416 shown.*125 Success.*259 Failure.*32 Uncertain/);
});
test('transient label failure remains visible, human labels work, and Refresh can recover', async () => {
  let fail = true;
  const api = setup(async () => ({ok:!fail,json:async () => data}));
  await api.load();
  assert.match(api.summary([], 'auto'), /unavailable.*Refresh/);
  assert.equal(api.outcome({assessment:{label:'Success',eligibility:'included'}}, 'human'), 'Success');
  fail = false; await api.load();
  assert.equal(api.outcome(data.runs[0], 'auto'), data.runs[0].auto_assessment.label);
});
test('source selector recolors the existing Cloud without refetching or changing saved assessments', async () => {
  const c = require('./helpers/past-runs.cjs')();
  c.window.yamRunLabels = {load:async () => {}, summary:(_, source) => source};
  c.events['blupe-robot-selected']({detail:'yam-1'});
  const run = {episode_id:'ep_selected',robot_id:'yam-1',prompt:'Lift',xyz:[0,0,0],assessment:{label:'Success',eligibility:'included'}};
  c.answer(c.requests[0],[run]); await c.flush();
  assert.equal(c.cloud.rows[0].label_source, 'auto');
  c.nodes.get('pastRunsLabelSource').value = 'human';
  c.nodes.get('pastRunsLabelSource').emit('change');
  assert.equal(c.cloud.rows[0].label_source, 'human');
  assert.equal(c.cloud.rows[0].assessment, run.assessment);
  assert.equal(c.cloud.rows[0].xyz, run.xyz);
  assert.equal(c.nodes.get('pastRunsLabelSummary').textContent, 'human');
  assert.equal(c.storage.get('yam-run-label-source'), 'human');
  assert.equal(c.requests.length, 1);
});
