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
test('hover requests only its detail, discards late responses, plays muted real source with saved layout and tears down previous playback',async()=>{
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
 c.preview.show(run('ep_c'),c.point);assert.equal(clip.pauses,1);assert.equal(clip.src,'');assert.equal(c.layouts[0].disposed,true);
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
