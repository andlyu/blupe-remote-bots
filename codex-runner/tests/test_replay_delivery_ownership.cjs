const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(process.env.REPLAY_PROGRESS_SOURCE||path.join(__dirname,'../static/replay-progress.js'),'utf8');
test('history-owned quick delivery is not restarted by later terminal observations',()=>{
 const nodes={},requests=[],timers=[];let owns=false;
 const element=()=>({children:[],hidden:false,open:true,paused:false,currentTime:1,ended:false,listeners:{},
  setAttribute(){},removeAttribute(){},append(...x){this.children.push(...x)},after(x){nodes[x.id]=x},addEventListener(n,f){this.listeners[n]=f}});
 const parent=element(),player=element();player.parentElement=parent;nodes.pastRunVideo=player;nodes.pastRunDialog=element();nodes.pastRunDialog.open=false;
 const window={addEventListener(){},yamReplayHistory:{openRun(){}},yamReplayReview:{
  observe(state){if(state.status==='stopped'&&!owns){owns=true;nodes.pastRunDialog.open=true}},ownsQuick(){return owns}}};
 vm.runInNewContext(source,{window,document:{readyState:'complete',body:{dataset:{}},getElementById:id=>nodes[id],createElement:element},
  location:{search:''},URLSearchParams,Date,setTimeout(f){timers.push(f);return timers.length},clearTimeout(){},
  fetch(url){requests.push(url);return new Promise(()=>{})},encodeURIComponent});
 const state=status=>({session_id:'sess_exact',episode_id:'ep_exact',status});
 window.yamReplayReview.observe(state('running'),'robot','csrf');
 window.yamReplayReview.observe(state('stopped'),'robot','csrf');
 assert.equal(requests.length,0,'history owns the first lookup');
 // History has handed its clip to the player and released ownsQuick. Force the
 // same interleaving for eight later status observations: no second owner.
 for(let i=0;i<8;i++){
  owns=false;
  // The underlying history observer has already completed this run.
  const original=window.yamReplayReview.ownsQuick;window.yamReplayReview.ownsQuick=()=>false;
  window.yamReplayReview.observe(state('stopped'),'robot','csrf');
  window.yamReplayReview.ownsQuick=original;
 }
 assert.equal(requests.length,0,'a finished history handoff must not start another readiness poll');
});
