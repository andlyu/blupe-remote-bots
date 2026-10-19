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
    'clearRunHistoryEmail','moreMyRuns','refreshPastRuns','past-runs','pastRunTitle','pastRunPrompt','pastRunError','pastRunMetricsSummary','pastRunMetricsChart','prompt','email','myRunsStatus'];
  for(const id of ids)nodes.set(id,element());
  const window={addEventListener(name,fn){events[name]=fn},history:{replaceState(){}},yamReplayHistory:{openRun(run){window.yamReplayReview.ready();opened.push(run)},refresh(){}}};
  vm.runInNewContext(source,{document:{getElementById:id=>nodes.get(id),createElement:element},window,
    renderRunMetrics(node,metrics){node.textContent=JSON.stringify(metrics);summaries.push(metrics)},renderStepMetricsChart(node,timings){charts.push(timings)},
    localStorage:{getItem:k=>stored[k]||null,setItem:(k,v)=>stored[k]=v},location:{search:'',href:'https://robot.example/'},URL,URLSearchParams,Date,
    setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id),
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}});
  const flush=()=>new Promise(setImmediate);
  const answer=(req,runs=[])=>req.resolve({ok:true,json:async()=>({runs,next_offset:null})});
  const state=(status,extras={})=>window.yamReplayReview.observe({session_id:'mine',status,episode_id:'ep_own',...extras},'yam-1','csrf-token');
  events['blupe-robot-selected']({detail:'yam-1'});
  return {nodes,events,requests,timers,opened,window,flush,answer,state,stored,summaries,charts};
}
test('only an observed own run auto-opens once; it transitions from processing to playable',async()=>{
  const c=setup(); c.state('idle',{public_run:{status:'running',episode_id:'ep_other'}});
  assert.equal(c.nodes.get('pastRunDialog').open,false);
  c.answer(c.requests[0]);await c.flush();
  c.state('running');c.state('stopped');
  assert.equal(c.nodes.get('pastRunDialog').open,true);assert.equal(c.nodes.get('replayProcessing').hidden,false);
  const poll=c.requests.find(r=>r.url.includes('episode_id=ep_own'));c.answer(poll);await c.flush();
  assert.equal(c.timers.size,1);
  const timer=[...c.timers.values()][0]; timer();
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
test('email search uses a CSRF-protected body and merges public browser identifiers',async()=>{
  const c=setup();c.state('running');c.nodes.get('runHistoryEmail').value='person@example.com';
  c.nodes.get('runHistorySearch').emit('submit',{preventDefault(){}});
  const request=c.requests.at(-1), body=JSON.parse(request.options.body);
  assert.equal(request.url,'/api/my-runs');assert.equal(request.options.method,'POST');
  assert.equal(body.email,'person@example.com');assert.deepEqual(body.episode_ids,['ep_own']);
  assert.equal(request.options.headers['X-YAM-Runner-Token'],'csrf-token');
  c.answer(request,[{episode_id:'ep_old',prompt:'Earlier run',video_url:'https://example/video'}]);await c.flush();
  assert.equal(c.nodes.get('myRunsList').children.length,1);
});

test('summary and charts appear immediately and update while only the video is processing',async()=>{
  const c=setup(); c.state('running');
  const metrics={model_s:12,execution_s:4,left_path_m:.5}, timings=[{step:1,model_s:12}];
  c.state('stopped',{runner_name:'Andrew',run_metrics:metrics,step_timings:timings});
  assert.equal(c.nodes.get('pastRunTitle').textContent,'Andrew · Recent run');
  assert.deepEqual(c.summaries.at(-1),metrics);assert.deepEqual(c.charts.at(-1),timings);
  assert.equal(c.nodes.get('replayProcessing').hidden,false);
  const poll=c.requests.find(r=>r.url.includes('episode_id='));
  c.answer(poll,[{episode_id:'ep_own',robot_id:'yam-1',runner_name:'Andrew',result:'Success',ending_reason:'Reported complete',run_metrics:metrics,step_timings:timings,video_url:null,video_duration_s:null}]);await c.flush();
  assert.equal(c.opened.length,0);assert.equal(c.nodes.get('replayProcessing').hidden,false);
  assert.equal(c.nodes.get('pastRunDetails').textContent,'Success: Reported complete');
  assert.deepEqual(c.summaries.at(-1),metrics);assert.equal(c.timers.size,1);
});
