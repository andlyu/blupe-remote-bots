const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8').split('\n})();')[0]+'\n})();';
test('Table recording blocks wait for robot selection, ignore stale responses and open shared details', async () => {
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
  row.children[0].emit('click');assert.equal(c.opened[0].id,'ep_one');
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

test('incumbent previews are muted, exclusive and pause on replay, view switch, exit and hidden page',async()=>{
  const c=require('./helpers/past-runs.cjs')();
  c.events['blupe-robot-selected']({detail:'yam-1'});
  const run={episode_id:'ep_one',episode_index:1,prompt:'Move block',started_at:1,model:'M',
    video_url:'https://example.com/previews/one.mp4',original_video_url:'https://example.com/videos/one.mp4',
    camera_order:['top','left','right'],video_layout:'observer-focus',compressed:true};
  c.answer(c.requests[0],[run,{...run,episode_id:'ep_two',video_url:'https://example.com/previews/two.mp4'}]);await c.flush();
  const cards=c.nodes.get('pastRunsList').children.map(item=>item.children[0]);
  const videos=cards.map(card=>card.children.find(child=>child.tag==='video'));
  cards[0].emit('pointerenter',{pointerType:'touch'});assert.equal(videos[0].plays,0);
  cards[0].emit('pointerenter',{pointerType:'mouse'});assert.equal(videos[0].plays,1);
  assert.equal(videos[0].muted,true);assert.equal(videos[0].playbackRate,1);
  cards[1].emit('focus');assert.equal(videos[0].pauses,1);assert.equal(videos[1].plays,1);
  cards[1].emit('pointerleave');assert.equal(videos[1].pauses,1);
  cards[0].emit('click');assert.equal(c.nodes.get('pastRunVideo').src,run.video_url);assert.equal(c.nodes.get('pastRunDialog').open,true);
  cards[0].emit('pointerenter',{pointerType:'mouse'});assert.equal(videos[0].plays,1,'Modal playback suppresses hover previews');
  c.nodes.get('pastRunDialog').close();cards[0].emit('pointerenter',{pointerType:'mouse'});
  const before=videos[0].pauses;c.document.hidden=true;c.events.visibilitychange();assert.equal(videos[0].pauses,before+1);c.document.hidden=false;
  const played=videos[0].plays;c.window.matchMedia=()=>({matches:true});cards[0].emit('pointerenter',{pointerType:'mouse'});assert.equal(videos[0].plays,played,'Reduced motion disables autoplay previews');c.window.matchMedia=()=>({matches:false});
  cards[0].emit('pointerenter',{pointerType:'mouse'});
  c.nodes.get('pastRunsCloudView').emit('click');assert.ok(videos[0].pauses>=2);
});

test('recording blocks retain reason, assessment text and the live-speed replay action',async()=>{
 const c=require('./helpers/past-runs.cjs')();c.events['blupe-robot-selected']({detail:'yam-1'});
 const run={episode_id:'ep_one',episode_index:1,prompt:'Move block',started_at:1,model:'M',
   video_url:'https://example.com/previews/one.mp4',original_video_url:'https://example.com/videos/one.mp4',camera_order:[],
   result:'Stopped',ending_reason:'Time limit',assessment:{label:'Success',correct:1,incorrect:2,eligibility:'excluded'}};
 c.answer(c.requests[0],[run]);await c.flush();
 const block=c.nodes.get('pastRunsList').children[0];
 const reason=block.children.find(child=>child.tag==='details');
 assert.equal(reason.children[1].textContent,'Ending reason: Time limit');
 assert.match(block.children.find(child=>child.className==='pastRunAssessment help').textContent,/Runner: Success · excluded · 1 correct \/ 2 incorrect/);
 block.children.find(child=>child.tag==='button' && child.textContent==='Live speed').emit('click');
 assert.equal(c.nodes.get('pastRunVideo').src,run.original_video_url);assert.equal(c.nodes.get('pastRunVideo').playbackRate,1);
});

test('Cloud lazily requests only its preview detail and clears media scope on search, view, robot and hidden page',async()=>{
 const c=require('./helpers/past-runs.cjs')();c.events['blupe-robot-selected']({detail:'yam-1'});
 c.answer(c.requests[0],[]);await c.flush();c.nodes.get('pastRunsCloudView').emit('click');
 c.answer(c.requests[1],[{episode_id:'ep_one',prompt:'Task',xyz:[0,0,0]}]);await c.flush();
 assert.equal(c.requests.length,2,'Cloud catalog load does not fetch all recording details');
 const options=c.cloudPreview.options,signal={};
 const loading=options.loadRun({episode_id:'ep_one'},signal);
 assert.match(c.requests[2].url,/api\/past-runs\?episode_id=ep_one&robot_id=yam-1/);
 assert.equal(c.requests[2].options.signal,signal);
 c.answer(c.requests[2],[{episode_id:'ep_wrong',robot_id:'yam-1'},{episode_id:'ep_one',robot_id:'other'},{episode_id:'ep_one',robot_id:'yam-1',video_url:'real.mp4'}]);
 assert.equal((await loading).video_url,'real.mp4');
 assert.equal(options.canPlay(),true);
 let stopped=c.cloudPreview.hides;c.document.hidden=true;c.events.visibilitychange();assert.ok(c.cloudPreview.hides>stopped);assert.equal(options.canPlay(),false);c.document.hidden=false;
 stopped=c.cloudPreview.hides;c.search('apple');assert.ok(c.cloudPreview.hides>stopped);
 stopped=c.cloudPreview.hides;c.nodes.get('pastRunsTableView').emit('click');assert.ok(c.cloudPreview.hides>stopped);assert.equal(options.canPlay(),false);
 stopped=c.cloudPreview.hides;c.events['blupe-robot-selected']({detail:'other'});assert.ok(c.cloudPreview.hides>stopped);
});
