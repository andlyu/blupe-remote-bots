const test=require('node:test'),assert=require('node:assert/strict');
const {openDataChatReplay}=require('../static/run-data-chat.js');
const citation={episode_id:'ep_a',robot_id:'yam-1'};
test('evidence navigation loads actual replay detail without waiting for policy status initialization',async()=>{
 let opened=null,url='',headers;
 const detail={...citation,video_url:'https://example.com/public.mp4',video_duration_s:1};
 const result=await openDataChatReplay(citation,async(u,o)=>{url=u;headers=o.headers;return {ok:true,json:async()=>({runs:[detail]})};},()=> 'yam-1',run=>opened=run);
 assert.equal(result,true);assert.equal(opened,detail);assert.match(url,/episode_id=ep_a&robot_id=yam-1/);assert.equal(headers['X-Blupe-Robot'],'yam-1');
});
test('evidence navigation rejects wrong-run details, stale robots, and unavailable videos',async()=>{
 let robot='yam-1',opened=false;
 await assert.rejects(openDataChatReplay(citation,async()=>({ok:true,json:async()=>({runs:[{...citation,episode_id:'ep_b',video_url:'wrong'}]})}),()=>robot,()=>opened=true),/not ready/);
 const result=await openDataChatReplay(citation,async()=>{robot='other';return {ok:true,json:async()=>({runs:[{...citation,video_url:'public'}]})};},()=>robot,()=>opened=true);
 assert.equal(result,false);assert.equal(opened,false);
 let fetched=false;assert.equal(await openDataChatReplay(citation,async()=>{fetched=true;},()=> 'other',()=>{}),false);assert.equal(fetched,false);
});
