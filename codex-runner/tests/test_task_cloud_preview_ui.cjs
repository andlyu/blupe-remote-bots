const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(){
 const source=fs.readFileSync(path.join(__dirname,'../static/task-cloud.js'),'utf8'),loads=[],videos=[],layouts=[],timers=new Map();let timerId=0;
 const make=()=>({children:[],events:{},plays:0,pauses:0,attributes:{},
  append(...nodes){this.children.push(...nodes)},replaceChildren(){this.children=[]},
  addEventListener(name,fn){this.events[name]=fn},emit(name){this.events[name]?.()},
  setAttribute(name,value){this.attributes[name]=value},removeAttribute(name){delete this.attributes[name];if(name==='src')this.src=''},
  pause(){this.pauses++},load(){},play(){this.plays++;return this.playFailure?Promise.reject(Error()):Promise.resolve()}});
 const media=make(),title={},status={},root={hidden:true,dataset:{},style:{},offsetWidth:260,offsetHeight:250,
  querySelector(selector){return selector.endsWith('Media')?media:selector.endsWith('Title')?title:status}};
 const window={},document={createElement(){const video=make();videos.push(video);return video}};
 vm.runInNewContext(source,{window,document,AbortController,setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout(id){timers.delete(id)}});
 let allowed=true,reduced=false;
 const preview=window.yamTaskCloud.createPreview(root,{
  loadRun(run,signal){return new Promise((resolve,reject)=>loads.push({run,signal,resolve,reject}))},
  source:run=>({url:run.video_url,rate:run.compressed?1:10}),
  layout(video,roles,layout){const call={video,roles,layout,disposed:false};layouts.push(call);return()=>call.disposed=true},
  canPlay:()=>allowed,reducedMotion:()=>reduced});
 const point={x:980,y:530,width:1000,height:540};
 return{preview,root,media,title,status,videos,loads,layouts,timers,point,allow:v=>allowed=v,reduce:v=>reduced=v,flush:()=>new Promise(setImmediate)};
}
const run=id=>({episode_id:id,prompt:'Task '+id});
const detail=id=>({...run(id),video_url:'https://example.com/previews/'+id+'.mp4',camera_order:['observer','left','top','right'],video_layout:'observer-focus',compressed:true});
test('hover requests only its detail, discards late responses, plays saved layout and parks previous playback',async()=>{
 const c=setup();const first=c.preview.show(run('ep_a'),c.point);
 assert.equal(c.loads.length,1);assert.equal(c.status.textContent,'Loading video…');assert.equal(c.videos.length,0);
 const second=c.preview.show(run('ep_b'),c.point);assert.equal(c.loads[0].signal.aborted,true);
 c.loads[1].resolve(detail('ep_b'));await second;
 assert.equal(c.videos.length,1);const clip=c.videos[0];
 assert.equal(clip.src,detail('ep_b').video_url);assert.equal(clip.plays,1);assert.equal(clip.muted,true);assert.equal(clip.loop,true);assert.equal(clip.playbackRate,1);
 assert.equal(c.layouts[0].layout,'observer-focus');assert.deepEqual(c.layouts[0].roles,['observer','left','top','right']);
 assert.doesNotMatch(c.status.textContent,/Playing/,'source assignment and play promise are not playback evidence');
 clip.emit('playing');assert.match(c.status.textContent,/Playing muted/);clip.emit('waiting');assert.equal(c.status.textContent,'Buffering video…');
 c.loads[0].resolve(detail('ep_a'));await first;assert.equal(c.root.dataset.episodeId,'ep_b');assert.equal(c.videos.length,1);
 await c.preview.show(run('ep_b'),{...c.point,x:200});assert.equal(c.loads.length,2,'same point does not refetch');
 c.preview.show(run('ep_c'),c.point);assert.equal(clip.pauses,1);assert.equal(clip.src,detail('ep_b').video_url);assert.equal(c.layouts[0].disposed,true);
 c.preview.hide();assert.equal(c.loads[2].signal.aborted,true);assert.equal(c.root.hidden,true);
 c.loads[2].resolve(detail('ep_c'));await c.flush();assert.equal(c.videos.length,1);
 assert.ok(parseInt(c.root.style.left)>=8);assert.ok(parseInt(c.root.style.top)>=8);
});
test('truthful unavailable, zero-duration, reduced-motion and media-error states; disabled scope never fetches',async()=>{
 const c=setup();let showing=c.preview.show(run('ep_a'),c.point);c.loads[0].resolve({...detail('ep_a'),video_duration_s:0});await showing;
 assert.match(c.status.textContent,/No preview available/);assert.equal(c.videos.length,0);
 showing=c.preview.show(run('ep_b'),c.point);c.loads[1].reject(Error());await showing;assert.match(c.status.textContent,/unavailable/);
 c.reduce(true);showing=c.preview.show(run('ep_c'),c.point);c.loads[2].resolve(detail('ep_c'));await showing;
 assert.equal(c.videos[0].plays,0);assert.match(c.status.textContent,/reduced motion/);
 c.videos[0].emit('error');assert.match(c.status.textContent,/unavailable/);
 c.allow(false);await c.preview.show(run('ep_d'),c.point);assert.equal(c.loads.length,3);assert.equal(c.root.hidden,true);
});
test('native preparation polls lazily, plays only when ready, and cancels retries on exit',async()=>{
 const c=setup();let showing=c.preview.show(run('ep_a'),c.point);
 c.loads[0].resolve({...run('ep_a'),video_status:'processing'});await c.flush();
 assert.equal(c.status.textContent,'Preparing recorded video…');assert.equal(c.videos.length,0);
 [...c.timers.values()][0]();await c.flush();assert.equal(c.loads.length,2);
 c.loads[1].resolve(detail('ep_a'));await showing;assert.equal(c.videos[0].plays,1);
 showing=c.preview.show(run('ep_b'),c.point);c.loads[2].resolve({...run('ep_b'),video_status:'processing'});await c.flush();
 c.preview.hide();await showing;assert.equal(c.root.hidden,true);assert.equal(c.loads[2].signal.aborted,true);
 assert.equal(c.loads.length,3,'Cancelled native preparation cannot fetch or play a later recording');
});
test('nearby previews warm without playing and a revisit reuses the buffered player',async()=>{
 const c=setup();
 assert.equal(typeof c.preview.warm,'function');
 c.preview.warm([run('ep_a')]);assert.equal(c.loads.length,1);
 c.loads[0].resolve(detail('ep_a'));await c.flush();
 assert.equal(c.videos.length,1);assert.equal(c.videos[0].plays,0);
 assert.equal(c.videos[0].preload,'auto');
 await c.preview.show(run('ep_a'),c.point);
 assert.equal(c.loads.length,1,'hover uses the warmed details');assert.equal(c.videos[0].plays,1);
 await c.preview.show(null,null);assert.equal(c.root.hidden,true);
 assert.equal(c.videos[0].src,detail('ep_a').video_url,'pointer exit preserves the buffer');
 await c.preview.show(run('ep_a'),c.point);
 assert.equal(c.loads.length,1);assert.equal(c.videos.length,1);assert.equal(c.videos[0].plays,2);
 c.preview.hide();assert.equal(c.videos[0].src,'','leaving the cloud releases cached media');
});
test('speculation is bounded, cancelled on cleanup, and disabled for reduced motion',async()=>{
 const c=setup();
 assert.equal(typeof c.preview.warm,'function');
 c.reduce(true);c.preview.warm([run('ep_a')]);assert.equal(c.loads.length,0);
 c.reduce(false);c.preview.warm([run('ep_a'),run('ep_b'),run('ep_c')]);assert.equal(c.loads.length,2);
 c.preview.hide();assert.ok(c.loads.every(load=>load.signal.aborted));
 for(const load of c.loads)load.resolve(detail(load.run.episode_id));
 await c.flush();assert.equal(c.videos.length,0,'late speculative responses cannot recreate players');
});
test('a hover joins an in-flight warm request and only three players remain buffered',async()=>{
 const c=setup();c.preview.warm([run('ep_a')]);
 const showing=c.preview.show(run('ep_a'),c.point);assert.equal(c.loads.length,1);
 c.loads[0].resolve(detail('ep_a'));await showing;
 for(const id of ['ep_b','ep_c','ep_d']){
  const next=c.preview.show(run(id),c.point);c.loads.at(-1).resolve(detail(id));await next;
 }
 assert.equal(c.videos[0].src,'','least-recent player was evicted');
 assert.equal(c.videos.filter(video=>video.src).length,3);
 assert.equal(c.videos.filter(video=>video.plays>0&&video.pauses===0).length,1,'only active player can play');
 c.preview.hide();assert.ok(c.videos.every(video=>!video.src));
});
test('matching episode IDs on different robots never reuse another station’s preview',async()=>{
 const c=setup();let showing=c.preview.show({...run('ep_a'),robot_id:'one'},c.point);
 c.loads[0].resolve(detail('ep_a'));await showing;
 showing=c.preview.show({...run('ep_a'),robot_id:'two'},c.point);
 assert.equal(c.loads.length,2);c.loads[1].resolve({...detail('ep_a'),video_url:'https://example.com/two.mp4'});await showing;
 assert.equal(c.videos[1].src,'https://example.com/two.mp4');
});
test('ready catalog hints start media immediately without a hover-detail request',async()=>{
 const c=setup();await c.preview.show({...run('ep_a'),preview:detail('ep_a')},c.point);
 assert.equal(c.loads.length,0);assert.equal(c.videos[0].src,detail('ep_a').video_url);assert.equal(c.videos[0].plays,1);
 assert.equal(c.layouts[0].layout,'observer-focus');
});
test('Cloud reuses recent ready Table media without retaining assessment data',async()=>{
 const c=require('./helpers/past-runs.cjs')('','table');c.events['blupe-robot-selected']({detail:'yam-1'});
 const row={...detail('ep_a'),robot_id:'yam-1',assessment:{label:'Success'},replay_speed:2};
 c.answer(c.requests[0],[row]);await c.flush();c.nodes.get('pastRunsCloudView').emit('click');
 c.answer(c.requests[1],[run('ep_a')]);await c.flush();
 assert.equal(c.cloud.rows[0].preview.video_url,row.video_url,'Known recent cache clips override slower archive hints');
 const detailFromCache=await c.cloudPreview.options.loadRun({...run('ep_a'),robot_id:'yam-1'},new AbortController().signal);
 assert.equal(c.requests.length,2,'No additional hover detail request');
 assert.equal(detailFromCache.video_url,row.video_url);assert.equal(detailFromCache.replay_speed,2);
 assert.equal(detailFromCache.assessment,undefined,'Media reuse does not cache votes or labels');
});
test('Custom end-point becomes the active provider and focuses its input without navigating',()=>{
 const full=fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
 const handler=full.match(/function selectModelChoice\(event\) \{[^]*?\n  \}/)[0];
 let changes=0,focus=0,opened=0;
 const provider={value:'dream',dispatchEvent(){changes++}};
 const picker={selectedOptions:[{dataset:{provider:'custom_endpoint'}}]};
 const nodes={modelSettings:{hidden:true},customEndpoint:{focus(){focus++}}};
 const select=vm.runInNewContext('('+handler+')',{$:id=>nodes[id],provider,Event:class{},
  updateComposer(){},showComposerOptions(value){assert.equal(value,true);opened++},
  options:{matches:()=>false},window:{}});
 select({currentTarget:picker});select({currentTarget:picker});
 assert.equal(provider.value,'custom_endpoint');assert.equal(changes,1);
 assert.equal(focus,2);assert.equal(opened,2);
 assert.ok(!handler.includes('.click()'),'Selecting a provider never opens documentation');
 const html=fs.readFileSync(path.join(__dirname,'../static/hosted.html'),'utf8');
 assert.match(html, /id="customEndpoint"[^]*?id="customEndpointHelp"[^]*?docs\/API\.md#custom-end-point/);
 assert.match(full,/payload\.endpoint = \$\('customEndpoint'\)\.value\.trim\(\)/);
});
