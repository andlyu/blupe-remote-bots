const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/replay-history.js'),'utf8');
const preview={video_url:'https://example.test/clip.mp4',video_duration_s:3,compressed:true};
const row=(id,prompt='Pick apple',xyz=[0,0,0],robot_id='yam-1')=>({episode_id:id,prompt,xyz,robot_id,preview,model:'Test policy'});
function setup(options={}){
 const nodes=new Map(),events={},requests=[],observers=[];
 function element(tag='div'){
  const classes=new Set(),attrs=new Map(),n={tag,children:[],listeners:{},classList:{contains:x=>classes.has(x),add:x=>classes.add(x),remove:x=>classes.delete(x)},
   addEventListener(k,f){(this.listeners[k]||=[]).push(f)},emit(k,event={}){for(const f of this.listeners[k]||[])f(event)},
   append(...children){for(const c of children){c.parent=this;this.children.push(c)}},replaceChildren(...children){this.children=[];this.append(...children)},
   setAttribute(k,v){attrs.set(k,v)},hasAttribute:k=>attrs.has(k),removeAttribute:k=>attrs.delete(k),
   pause(){this.pauses=(this.pauses||0)+1},load(){},play(){return Promise.resolve()},show(){this.open=true;this.shows=(this.shows||0)+1},close(){this.open=false;this.emit('close')},
   contains(other){for(let p=other;p;p=p.parent)if(p===this)return true;return false},focus(){this.focused=true},isConnected:true};
  Object.defineProperty(n,'src',{get:()=>attrs.get('src'),set:v=>attrs.set('src',v)});return n;
 }
 for(const id of ['pastRunDialog','runSidebarBody','similarRunsList','similarRunsStatus','similarRunsScore','moreSimilarRuns','similarRunsSentinel','pastRunVideo','pastRunsLabelSource'])nodes.set(id,element());
 nodes.get('pastRunDialog').classList.add('runSidebar');
 const body=element(),focus=element(),document={body,activeElement:focus,getElementById:id=>nodes.get(id),createElement:element,addEventListener:(k,f)=>events[k]=f};
 const window={addEventListener:(k,f)=>events[k]=f,yamRunLabels:{load:async()=>{},outcome:(_,s)=>s==='human'?'Failure':'Success'},yamReplayHistory:{selectRun:run=>window.selected=run},matchMedia:()=>({matches:false})};
 class Observer{constructor(callback,options){this.callback=callback;this.options=options;this.targets=[];observers.push(this)}observe(x){this.targets.push(x)}disconnect(){this.disconnected=true}fire(items){this.callback(items.map(target=>({target,isIntersecting:true})))}}
 vm.runInNewContext(source,{window,document,...(options.observer===false?{}:{IntersectionObserver:Observer}),AbortController,encodeURIComponent,URLSearchParams,fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
 const flush=()=>new Promise(setImmediate),answer=(request,runs)=>request.resolve({ok:true,json:async()=>({runs})});
 return {window,document,nodes,body,events,requests,observers,flush,answer,rank:window.yamSimilarRuns.rank};
}
test('related ranking stays on the robot, excludes self/unpublished/empty media and prefers exact prompts',()=>{
 const c=setup(),selected=row('ep_self'),exact=row('ep_exact','PICK APPLE!',[.19,0,0]),near=row('ep_near','Move apple',[.01,0,0]);
 const data=[selected,near,exact,row('ep_wordmatch','Pick big apple',[.35,0,0]),row('ep_projection_collision','Wave hi',[0,0,0]),row('ep_far','Other',[.4,0,0]),row('ep_wrong','Pick apple',[0,0,0],'other'),{...row('ep_empty'),preview:{...preview,video_duration_s:0}}, {...row('ep_receipt'),preview:null}];
 assert.deepEqual(Array.from(c.rank(selected,data),r=>r.episode_id),['ep_exact','ep_wordmatch','ep_near']);
 const fallback={...selected,xyz:null};assert.equal(c.rank(fallback,[row('ep_words','Pick green apple',null),row('ep_unrelated','Stack tower',null)]).length,1);
 assert.equal(c.rank(selected,Array.from({length:60},(_,i)=>row('ep_'+i))).length,40);
});
test('similar success summary uses only the first ten neighbors and reports label coverage for the selected source',()=>{
 const c=setup(),labels=['Success','Success','Failure','Failure','Failure','Uncertain','Uncertain','Unscored','Unscored','Unscored','Success'];
 c.window.yamRunLabels.outcome=(run,source)=>source==='auto'?run.testOutcome:'Failure';
 const rows=labels.map((testOutcome,i)=>({...row('ep_'+i),testOutcome}));
 const text=c.window.yamSimilarRuns.summary(rows,'auto');
 assert.match(text,/40\.0% success \(2\/5 Success\/Failure labels\).*10 closest/);assert.match(text,/2 Uncertain and 3 unlabeled or excluded/);assert.match(text,/Auto-labeled/);
 assert.match(c.window.yamSimilarRuns.summary(rows,'human'),/0\.0% success \(0\/10 Success\/Failure labels\).*Human-labeled/);
 assert.match(c.window.yamSimilarRuns.summary(rows.slice(0,3),'auto'),/3 available similar runs/);
 assert.match(c.window.yamSimilarRuns.summary(rows.slice(5,8),'auto'),/No Success\/Failure labels/);
 assert.equal(c.window.yamSimilarRuns.summary([],'auto'),'No similar published runs to score.');
});
test('related catalogs and scores follow active robot/model/search filters and reject stale filter responses',async()=>{
 const c=setup();
 c.window.yamRunSidebar.setCatalog([],{robot:'yam-1',complete:false,source:'auto',filters:{models:['Policy A'],query:'apple'}});
 c.window.yamRunSidebar.open(row('ep_self'));assert.match(c.requests[0].url,/model=Policy%20A&q=apple/);
 c.window.yamRunSidebar.setCatalog([],{robot:'yam-1',complete:false,source:'auto',filters:{models:['Policy B'],query:'apple'}});
 assert.equal(c.requests.length,2);assert.ok(c.requests[0].options.signal.aborted);assert.match(c.requests[1].url,/model=Policy%20B/);
 c.answer(c.requests[1],[row('ep_b')]);await c.flush();c.answer(c.requests[0],[row('ep_stale_a')]);await c.flush();
 c.nodes.get('similarRunsList').children[0].children[0].emit('click');assert.equal(c.window.selected.episode_id,'ep_b');assert.match(c.nodes.get('similarRunsScore').textContent,/1 available similar run/);
});
test('nonmodal inspector progressively appends related videos, bounds media and recalculates labels',async()=>{
 const c=setup(),rows=Array.from({length:24},(_,i)=>row('ep_'+i));c.window.yamRunSidebar.setCatalog(rows,{robot:'yam-1',complete:true,source:'auto'});
 c.window.yamRunSidebar.open(row('ep_self'));await c.flush();
 const dialog=c.nodes.get('pastRunDialog'),list=c.nodes.get('similarRunsList');assert.equal(dialog.shows,1);assert.ok(c.body.classList.contains('runSidebarOpen'));assert.equal(list.children.length,8);assert.equal(c.requests.length,0);
 const media=c.observers.find(o=>o.options.rootMargin==='80px 0px');media.fire(list.children);await c.flush();
 const loaded=list.children.filter(li=>li.children[0].children[0].hasAttribute('src')).length;assert.ok(loaded>0 && loaded<=6);
 const more=c.observers.find(o=>o.options.rootMargin==='0px 0px 120px 0px');more.fire([c.nodes.get('similarRunsSentinel')]);assert.equal(list.children.length,16);
 list.children[0].children[0].emit('click');assert.equal(c.window.selected.robot_id,'yam-1');
 c.window.yamRunSidebar.setSource('human');await c.flush();assert.match(list.children[0].children[0].children[1].children[1].textContent,/Human: Failure/);
 dialog.close();assert.ok(!c.body.classList.contains('runSidebarOpen'));assert.ok(c.observers.every(o=>o.disconnected));
});
test('switching runs discards stale catalog responses; closing aborts bounded preview requests',async()=>{
 const c=setup();c.window.yamRunSidebar.open(row('ep_a'));c.window.yamRunSidebar.open(row('ep_b'));assert.equal(c.requests.length,2);assert.ok(c.requests[0].options.signal.aborted);
 c.answer(c.requests[1],[row('ep_fresh')]);await c.flush();c.answer(c.requests[0],[row('ep_stale')]);await c.flush();
 c.window.yamRunSidebar.open(row('ep_c'));await c.flush();const list=c.nodes.get('similarRunsList');list.children[0].children[0].emit('click');assert.equal(c.window.selected.episode_id,'ep_fresh');
 const rows=Array.from({length:8},(_,i)=>({...row('ep_detail'+i),preview:null,original_available:true}));
 c.window.yamRunSidebar.setCatalog(rows,{robot:'yam-1',complete:true,source:'auto'});await c.flush();
 const media=c.observers.filter(o=>o.options.rootMargin==='80px 0px').at(-1);media.fire(list.children);assert.equal(c.requests.length,4,'only two detail requests start');
 c.nodes.get('pastRunDialog').close();assert.ok(c.requests.slice(2).every(r=>r.options.signal.aborted));
 for(const r of c.requests.slice(2))c.answer(r,[{...rows[0],video_url:preview.video_url}]);await c.flush();
 assert.equal(list.children.filter(li=>li.children[0].children[0].hasAttribute('src')).length,0);
});
test('fallback button loads later previews on keyboard focus without IntersectionObserver',async()=>{
 const c=setup({observer:false});c.window.yamRunSidebar.setCatalog(Array.from({length:18},(_,i)=>row('ep_'+i)),{robot:'yam-1',complete:true,source:'auto'});
 c.window.yamRunSidebar.open(row('ep_self'));await c.flush();c.nodes.get('moreSimilarRuns').emit('click');
 const button=c.nodes.get('similarRunsList').children[12].children[0],video=button.children[0];assert.ok(!video.hasAttribute('src'));
 button.emit('focus');await c.flush();assert.ok(video.hasAttribute('src'));button.emit('blur');assert.ok(!video.hasAttribute('src'));
});
test('Escape leaves a nested email/settings modal alone and otherwise closes the inspector',()=>{
 const c=setup();c.window.yamRunSidebar.open(row('ep_self'));let modal=true;c.document.querySelector=()=>modal?{}:null;
 c.events.keydown({key:'Escape',preventDefault(){}});assert.ok(c.nodes.get('pastRunDialog').open);
 modal=false;c.events.keydown({key:'Escape',preventDefault(){}});assert.ok(!c.nodes.get('pastRunDialog').open);
});
