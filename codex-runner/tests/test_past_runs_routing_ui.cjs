const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8').split('\n})();')[0]+'\n})();';
test('Table loads lightweight metadata, waits for robot selection and ignores a previous robot response', async () => {
  const c = require('./helpers/past-runs.cjs')();
  assert.equal(c.requests.length,0);
  c.events['blupe-robot-selected']({detail:'robot-3652c537a175cbae'});
  assert.match(c.requests[0].url,/api\/run-catalog.*robot_id=robot-3652c537a175cbae/);
  assert.match(c.nodes.get('datasetViewer').src,/Public-MakerMods-SO101-runs/);
  c.events['blupe-robot-selected']({detail:'so101'});
  c.answer(c.requests[0],[],100,101); await c.flush();
  assert.equal(c.nodes.get('pastRunsStatus').textContent,'Loading past runs…');
  const run={episode_id:'ep_one',prompt:'Move block',started_at:1,model:'M'};
  c.answer(c.requests[1],[run]);await c.flush();
  const row=c.nodes.get('pastRunsList').children[0];
  assert.equal(row.tag,'tr');assert.equal(row.children.length,6);
  assert.equal(row.children[0].children.length,1);
  row.children[0].children[0].emit('click');assert.equal(c.opened[0].id,'ep_one');
});

 test('robot switching uses browser history even with a local history function', async () => {
  const full = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
  const handler = full.match(/selector\.onchange = async \(\) => \{([\s\S]*?)\n      \};/)[1];
  let started = 0, replaced = 0;
  const node = {value:'so101', textContent:'', replaceChildren(){}};
  const context = {makerModsPage:false, makerModsRobot:'robot-3652c537a175cbae', robotCatalog:{robots:[]}, submitting:false, selector:node, selectedRobot:'yam-1', robotGeneration:0,
    URL, location:{href:'http://localhost/?robot_id=yam-1'},
    history:async()=>{}, window:{history:{replaceState(a,b,url){replaced++;assert.equal(url.searchParams.get('robot_id'),'so101');}},dispatchEvent(){}},
    CustomEvent:class {}, $:()=>node, document:{querySelectorAll:()=>[]}, buttons(){}, renderRobotStatus(){},
    start:async()=>{started++;}, csrf:'',active:false,ended:false,lastChatSnapshot:''};
  await vm.runInNewContext('(async()=>{'+handler+'})()',context);
  assert.equal(replaced,1); assert.equal(started,1);
});
