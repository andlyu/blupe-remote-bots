const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../static/replay-history.js'),'utf8');
function setup() {
  const nodes=new Map(), events={}, requests=[], timers=new Map(), opened=[], stored={}, summaries=[], charts=[]; let timerId=0;
  function element(){return {children:[],dataset:{},value:'',hidden:false,open:false,listeners:{},parentElement:{hidden:false},
    addEventListener(name,fn){(this.listeners[name] ||= []).push(fn)}, emit(name,event={}){for(const fn of this.listeners[name]||[])fn(event)},
    append(...children){this.children.push(...children)},replaceChildren(){this.children=[]},after(){},pause(){},removeAttribute(){},load(){},
    showModal(){this.open=true;this.opens=(this.opens||0)+1},close(){this.open=false;this.emit('close')},scrollIntoView(){},focus(){},remove(){}};}
  const ids=['myRunsList','pastRunDialog','pastRunVideo','replayProcessing','pastRunDetails','runHistorySearch','runHistoryEmail',
    'clearRunHistoryEmail','moreMyRuns','refreshPastRuns','past-runs','pastRunTitle','pastRunPrompt','pastRunError','pastRunMetricsSummary','pastRunMetricsChart','prompt','email','myRunsStatus','assessmentWindow'];
  for(const id of ids)nodes.set(id,element());
  const window={addEventListener(name,fn){events[name]=fn},history:{replaceState(){}},yamReplayHistory:{openRun(run){window.yamReplayReview.ready();opened.push(run)},refresh(){}}};
  vm.runInNewContext(source,{document:{getElementById:id=>nodes.get(id),createElement:element},window,
    renderRunMetrics(node,metrics){node.textContent=JSON.stringify(metrics);summaries.push(metrics)},renderStepMetricsChart(node,timings){charts.push(timings)},
    localStorage:{getItem(){throw Error('History must not read durable storage')},setItem(){throw Error('History must not write durable storage')}},location:{search:'',href:'https://robot.example/'},URL,URLSearchParams,Date,
    setTimeout(fn,delay){fn.delay=delay;timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id),
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}});
  const flush=()=>new Promise(setImmediate);
  const answer=(req,runs=[])=>req.resolve({ok:true,json:async()=>({runs,next_offset:null})});
  const state=(status,extras={})=>window.yamReplayReview.observe({session_id:'mine',status,episode_id:'ep_own',...extras},'yam-1','csrf-token');
  events['blupe-robot-selected']({detail:'yam-1'});
  return {nodes,events,requests,timers,opened,window,flush,answer,state,stored,summaries,charts,advance(delay){for(const [id,fn] of timers)if(fn.delay===delay){timers.delete(id);fn();break}}};
}
test('own run waits exactly five seconds while preview request starts immediately, then opens processing review once',async()=>{
  const c=setup(); c.state('idle',{public_run:{status:'running',episode_id:'ep_other'}});
  assert.equal(c.nodes.get('pastRunDialog').open,false);
  c.answer(c.requests[0]);await c.flush();
  c.state('running');c.state('stopped');
  assert.equal(c.nodes.get('pastRunDialog').open,false);assert.equal(c.nodes.get('assessmentWindow').hidden,false);
  const eager=c.requests.find(r=>r.url.includes('episode_id=ep_own'));assert.match(eager.url,/preview=1/);c.answer(eager);await c.flush();
  assert.equal([...c.timers.values()][0].delay,5000);c.advance(5000);
  assert.equal(c.nodes.get('pastRunDialog').open,true);assert.equal(c.nodes.get('replayProcessing').hidden,false);
  const poll=c.requests.at(-1);c.answer(poll);await c.flush();
  assert.equal(c.timers.size,1);
  c.advance(5000);
  const latest=c.requests.at(-1);c.answer(latest,[{episode_id:'ep_own',robot_id:'yam-1',video_url:'https://example/replay.mp4',video_duration_s:4}]);await c.flush();
  assert.equal(c.opened.length,1);assert.equal(c.nodes.get('replayProcessing').hidden,true);
  c.state('stopped');assert.equal(c.nodes.get('pastRunDialog').opens,1);
});
test('closing or switching robot prevents a late response reopening the replay',async()=>{
  for(const change of ['close','switch']){
    const c=setup();c.state('running');c.state('stopped');const poll=c.requests.find(r=>r.url.includes('episode_id='));
    if(change==='close')c.nodes.get('pastRunDialog').close();else c.events['blupe-robot-selected']({detail:'other'});
    c.answer(poll,[{episode_id:'ep_own',robot_id:'yam-1',video_url:'https://example/video',video_duration_s:2}]);await c.flush();
    assert.equal(c.opened.length,0);assert.equal(c.timers.size,0);
  }
});
test('personal history sends only pagination and the current session token',async()=>{
  const c=setup();c.state('running');
  const request=c.requests.find(r=>r.url==='/api/my-runs'), body=JSON.parse(request.options.body);
  assert.equal(request.options.method,'POST');assert.deepEqual(body,{offset:0});
  assert.equal(request.options.headers['X-YAM-Runner-Token'],'csrf-token');
  c.answer(request,[{episode_id:'ep_own',prompt:'Current run',video_url:'https://example/video'}]);await c.flush();
  assert.equal(c.nodes.get('myRunsList').children.length,1);
  assert.equal(c.nodes.get('myRunsStatus').textContent,'Showing runs from your current session.');
  assert.doesNotMatch(source,/runHistoryEmail|runHistorySearch|localStorage|sessionStorage/);
});
test('a new session clears old personal rows and ignores stale responses',async()=>{
  const c=setup();c.state('running');
  const old=c.requests.find(r=>r.url==='/api/my-runs');
  c.window.yamReplayReview.observe({status:'idle'},'yam-1','new-session-token');
  const current=c.requests.at(-1);
  assert.equal(current.options.headers['X-YAM-Runner-Token'],'new-session-token');
  c.answer(current);await c.flush();
  c.answer(old,[{episode_id:'ep_old',prompt:'Old session'}]);await c.flush();
  assert.equal(c.nodes.get('myRunsList').children.length,0);
  assert.equal(c.nodes.get('myRunsStatus').textContent,'No runs in this session yet.');
});

test('summary and charts appear immediately and update while only the video is processing',async()=>{
  const c=setup(); c.state('running');
  const metrics={model_s:12,execution_s:4,left_path_m:.5}, timings=[{step:1,model_s:12}];
  c.state('stopped',{runner_name:'Andrew',run_metrics:metrics,step_timings:timings});c.advance(5000);
  assert.equal(c.nodes.get('pastRunTitle').textContent,'Andrew · Recent run');
  assert.deepEqual(c.summaries.at(-1),metrics);assert.deepEqual(c.charts.at(-1),timings);
  assert.equal(c.nodes.get('replayProcessing').hidden,false);
  const poll=c.requests.at(-1);
  c.answer(poll,[{episode_id:'ep_own',robot_id:'yam-1',runner_name:'Andrew',result:'Success',ending_reason:'Reported complete',run_metrics:metrics,step_timings:timings,video_url:null,video_duration_s:null}]);await c.flush();
  assert.equal(c.opened.length,0);assert.equal(c.nodes.get('replayProcessing').hidden,false);
  assert.equal(c.nodes.get('pastRunDetails').textContent,'Model not recorded · version unknown · Success: Reported complete');
  assert.deepEqual(c.summaries.at(-1),metrics);assert.equal(c.timers.size,1);
});
