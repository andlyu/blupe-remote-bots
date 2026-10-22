const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('path').join(__dirname,'../static/stream-health.js'),'utf8');
let now=0,callback,interval,reconnects=0; const visibility={}; const reports=[];
const video={dataset:{transport:'webrtc'},readyState:4,paused:false,currentTime:0,seekable:{length:0},
 requestVideoFrameCallback(fn){callback=fn;return 1},cancelVideoFrameCallback(){},addEventListener(){}};
const badge={dataset:{}},detail={};const document={hidden:false,addEventListener:(name,fn)=>visibility[name]=fn};
const context={window:{addEventListener(){}},document,performance:{now:()=>now},setInterval:fn=>{interval=fn;return 1},clearInterval(){},console:{info(){}}};
vm.createContext(context);vm.runInContext(source,context);
const monitor=new context.window.YamStreamHealth(video,{badge,detail,recover:()=>reconnects++,report:r=>reports.push(r),clock:()=>now});
badge.dataset ||= {}; // Real DOM elements always have dataset.
assert.equal(monitor.snapshot().state,'connecting');
now=8100; interval(); assert.equal(monitor.snapshot().state,'stalled');assert.equal(reconnects,1);
for(let i=0;i<20;i++){now+=100;callback(now,{captureTime:now-200});}
interval();assert.equal(monitor.snapshot().state,'live');assert.equal(monitor.snapshot().fps,10);
assert.equal(badge.textContent,'Live video');
now+=2001;interval();assert.equal(monitor.snapshot().state,'stalled');assert.equal(monitor.stale(),true);
// The video clock advancing alone cannot turn the health green.
video.currentTime+=10;interval();assert.equal(monitor.snapshot().state,'stalled');
now+=6000;interval();assert.equal(reconnects,2);
callback(now,{captureTime:now-2001});interval();assert.equal(monitor.snapshot().state,'behind');assert.equal(monitor.stale(),false,'Behind playback stays visible while it catches up');
video.dataset.transport='hls';video.seekable={length:1,end:()=>30};video.currentTime=28.5;
callback(now,{});interval();assert.equal(monitor.snapshot().state,'delayed');
video.currentTime=1;interval();assert.equal(monitor.snapshot().state,'behind');
document.hidden=true;visibility.visibilitychange();assert.equal(monitor.snapshot().state,'paused');
now+=100000;interval();assert.equal(reconnects,2);
document.hidden=false;visibility.visibilitychange();assert.equal(monitor.snapshot().state,'behind','Resuming must not certify the old HLS buffer as fresh');
video.dataset.transport='webrtc';video.seekable={length:0};now+=100;callback(now,{captureTime:now-100});interval();assert.equal(monitor.snapshot().state,'live');
assert(reports.some(r=>r.state==='stalled'));assert(reports.filter(r=>r.state==='live').length>=2);
// A fresh decode of an old source frame still violates the budget.
video.yamCaptureAge=()=>2100;callback(now,{});assert.equal(monitor.snapshot().state,'behind');
video.yamCaptureAge=()=>100;callback(now,{captureTime:now-1900});
now+=101;assert.equal(monitor.snapshot().state,'behind','Age includes time spent displaying a frame');
monitor.reset();video.yamCaptureAge=()=>null;
video.dataset.transport='hls';video.seekable={length:1,end:()=>10};video.currentTime=9;
video.yamPlaybackDelay=()=>51000;
assert.equal(monitor.snapshot().state,'behind','A stale playlist must not look fresh just because the playhead reached its edge');
// Hidden source callbacks may pause while the visible canvas keeps decoding.
video.dataset.transport='webrtc';video.yamCaptureAge=()=>null;video.yamPlaybackDelay=()=>null;
monitor.reset();video.seekable={length:0};let decoded=1;
video.getVideoPlaybackQuality=()=>({totalVideoFrames:decoded,droppedVideoFrames:0});
for(let i=0;i<100;i++){now+=100;decoded++;monitor.presented(undefined,true);}
assert.equal(monitor.snapshot().state,'live');assert.equal(monitor.snapshot().fps,10);
const count=monitor.frameTimes.length;callback(now,{});
assert.equal(monitor.frameTimes.length,count,'Canvas and frame callback must not double count the same decoded frame');
now+=2100;video.currentTime+=10;monitor.presented(undefined,true);
assert.equal(monitor.snapshot().state,'stalled','An advancing audio clock cannot certify frozen video');
monitor.close();console.log('Stream startup failure, actual frames, freeze, recovery, lag, HLS, hidden-tab checks passed');
