const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(process.env.YAM_TEST_HOSTED_JS || require('node:path').join(__dirname,'../static/hosted.js'),'utf8');
const camera=src.slice(src.indexOf('  function camera(image)'),src.indexOf('  async function poll()',src.indexOf('  function camera(image)')));
function harness(role='observer', monitored=false, streamPath, native=false){
 let health;
 let now=0, video, readerOptions, destroyed=0, closed=0;const intervals=[],timers=new Map(),visibility={};let id=0;
 const label={textContent:''};
 const context={$:()=>null,csrf:null,synchronizedPanels:()=>{},ended:false,performance:{now:()=>now},location:{href:'https://test.invalid/'},URL,selectedRobot:'yam-1',
 setTimeout:f=>{timers.set(++id,f);return id},clearTimeout:i=>timers.delete(i),setInterval:f=>intervals.push(f),clearInterval:()=>{},
 fetch:async()=>{throw Error('WebRTC must not request HLS health')},AbortSignal,
 document:{hidden:false,addEventListener:(n,f)=>visibility[n]=f,createElement:()=>video={currentTime:0,seekable:{length:0},readyState:0,paused:true,events:{},dataset:{},setAttribute(){},removeAttribute(){},load(){},pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()},addEventListener(n,f){this.events[n]=f},getAttribute(){return null},canPlayType(){return 'probably'}}},
 window:{RTCPeerConnection:function(){},addEventListener(){},Hls:null},
 MediaMTXWebRTCReader:class{constructor(o){readerOptions=o}close(){closed++}},
 Hls:class{static isSupported(){return !native}static Events={ERROR:'error',MANIFEST_PARSED:'manifest'};constructor(config){this.config=config;this.events={}}on(n,f){this.events[n]=f}loadSource(u){this.url=u}attachMedia(v){v.hls=this}destroy(){destroyed++}}
 };context.window.Hls=context.Hls;context.window.MediaMTXWebRTCReader=context.MediaMTXWebRTCReader;
 if(monitored) context.window.YamStreamHealth=class {constructor(video, options){health=options;}};
 vm.createContext(context);vm.runInContext(camera+'\ncamera(image)',Object.assign(context,{image:{dataset:{camera:role,streamPath},alt:role,parentElement:{querySelector:()=>label},replaceWith(){}}}));
 return {get health(){return health},context,video,label,intervals,timers,visibility,get reader(){return readerOptions},get closed(){return closed},setNow(t){now=t}};
}
(async()=>{
 const h=harness();assert.equal(h.video.dataset.transport,'webrtc');const old=h.reader;
 old.onTrack({streams:[{}]});h.video.currentTime=1;h.video.readyState=4;h.video.events.timeupdate();assert.equal(h.label.textContent,'Live');
 await h.intervals[0]();assert.equal(h.video.dataset.transport,'webrtc');
 h.setNow(9000);await h.intervals[0]();assert.equal(h.video.dataset.transport,'hls');assert.equal(h.closed,1);assert.equal(h.video.hls.url,'/live-video/hls/observer/index.m3u8');
 const before=h.video.srcObject;old.onTrack({streams:[{stale:true}]});assert.equal(h.video.srcObject,before);
 h.video.currentTime=0;h.video.paused=false;h.video.events.timeupdate();assert.notEqual(h.label.textContent,'Live');
 const e=harness();e.reader.onError('ICE failed');assert.equal(e.video.dataset.transport,'hls');
 const t=harness();[...t.timers.values()][0]();assert.equal(t.video.dataset.transport,'hls');
 const sync=harness('synchronized');assert.equal(sync.video.dataset.transport,'webrtc');assert.equal(sync.reader.url,'https://test.invalid/synchronized/whep');
 sync.reader.onError('ICE failed');assert.equal(sync.video.dataset.transport,'hls');assert.equal(sync.video.hls.url,'/synchronized/index.m3u8');
 await sync.intervals[0]();assert.equal(sync.video.dataset.transport,'hls'); // no independent-camera health request
 const robo=harness('synchronized',false,'robo-house');
 assert.equal(robo.reader,undefined,'Robo-house avoids the stalling audio WebRTC relay');
 assert.equal(robo.video.dataset.transport,'hls');assert.equal(robo.video.hls.url,'/robo-house/index.m3u8');
 const yam=harness('synchronized',false,'synchronized-hd');
 assert.equal(yam.reader,undefined,'YAM HD must start directly without waiting for a WebRTC handshake or timeout');
 assert.equal(yam.video.dataset.transport,'hls');assert.equal(yam.video.hls.url,'/synchronized-hd/index.m3u8');
 assert.equal(yam.video.hls.config.liveSyncDuration,.5);
 assert.equal(yam.video.hls.config.liveSyncMode,'buffered','Catch-up must use buffered video instead of seeking into missing data');
 assert.equal(yam.video.hls.config.liveMaxLatencyDuration,1,'Reserve upstream time inside the two-second total budget');
 for (const path of ['synchronized-hd','robo-house']) {
  const publicView=harness('synchronized',false,path);const stream=publicView.video.hls;
  publicView.context.ended=true;await publicView.intervals[0]();
  assert.equal(publicView.video.hls,stream);
  publicView.video.readyState=4;publicView.video.currentTime=2;publicView.video.paused=false;
  publicView.video.events.timeupdate();
  assert.equal(publicView.label.textContent,'Live · delayed','A control-session expiry must not shut down public live video');
 }
 const privateView=harness('left');privateView.context.ended=true;await privateView.intervals[0]();
 assert.equal(privateView.video.paused,true,'Session-bound camera behavior is unchanged');
 const advancing=harness('synchronized',true);
 advancing.reader.onTrack({streams:[{}]});advancing.setNow(15000);
 advancing.video.currentTime=10;advancing.video.readyState=4;advancing.video.events.timeupdate();
 advancing.health.recover({state:'stalled'});
 assert.equal(advancing.video.dataset.transport,'webrtc','Missing presentation callbacks must not restart advancing playback');
 advancing.setNow(19000);advancing.health.recover({state:'stalled'});
 assert.equal(advancing.video.dataset.transport,'hls','A stopped media clock still recovers');
 const monitored=harness('synchronized',true);
 monitored.setNow(8100);monitored.health.recover();
 assert.equal(monitored.video.dataset.transport,'hls');
 const firstHls=monitored.video.hls;
 monitored.setNow(18100);monitored.health.recover();
 await monitored.intervals[0]();
 assert.equal(monitored.video.hls,firstHls,'HLS startup must not be interrupted by either watchdog');
 monitored.setNow(29100);monitored.health.recover();
 const pending=[...monitored.timers.keys()];assert.equal(pending.length,1);
 monitored.health.recover();assert.deepEqual([...monitored.timers.keys()],pending,'Do not postpone a pending reconnect');
 const l=harness('left');assert.equal(l.video.dataset.transport,'hls');
 const v=harness();v.context.document.hidden=true;v.visibility.visibilitychange();assert.equal(v.closed,1);v.context.document.hidden=false;v.visibility.visibilitychange();assert.equal(v.video.dataset.transport,'webrtc');
 const safari=harness('left',false,undefined,true);
 safari.video.seekable={length:1,start:()=>10,end:()=>60};safari.video.currentTime=12;
 safari.video.onprogress();assert.equal(safari.video.currentTime,59,'Native HLS uses the same one-second target');
 const yamSafari=harness('synchronized',false,'synchronized-hd',true);
 yamSafari.video.seekable={length:1,start:()=>10,end:()=>60};yamSafari.video.currentTime=12;
 yamSafari.video.onprogress();assert.equal(yamSafari.video.currentTime,59.5,'Native YAM also reserves upstream latency');
 const lagged=harness('synchronized',true);
 lagged.reader.onError('ICE failed');lagged.setNow(1000);
 lagged.video.seekable={length:1,start:()=>0,end:()=>60};lagged.video.currentTime=9;
 const sameHls=lagged.video.hls;
 lagged.health.recover({state:'behind'});
 assert.equal(lagged.video.currentTime,9,'The health monitor must not repeatedly seek while hls.js controls latency');
 assert.equal(lagged.video.hls,sameHls,'Catch up without restarting a playable HLS stream');
 lagged.health.recover({state:'behind'});
 assert.equal(lagged.video.hls,sameHls,'Do not cycle connections when the publisher has no newer frame yet');
 assert.equal(sync.video.hls.config.liveSyncDuration,1);
 assert.equal(sync.video.hls.config.liveMaxLatencyDuration,2);
 assert.equal(sync.video.hls.config.liveSyncDurationCount,undefined,'Segment duration must not multiply the latency budget');
 console.log('PASS: WebRTC playback, independent health, timeout/error/stall fallback, stale callbacks, zero-time disconnect, visibility reconnect, other-camera HLS.');
})().catch(e=>{console.error(e);process.exitCode=1});
