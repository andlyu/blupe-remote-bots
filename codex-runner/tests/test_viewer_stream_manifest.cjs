const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/../static/hosted.js','utf8');
const helper=source.slice(source.indexOf('function createViewerStreamResolver'),source.indexOf('function runComparisonBaseMetrics'));
const robot='robot-ba8413962083809c',old={path:'robo-house',cameras:['top','left','right']};
const manifest=JSON.parse(fs.readFileSync(__dirname+'/../config/robohouse-observer-viewer.json','utf8'));
function setup(data, fail=false){
 const ctx={AbortSignal,fetch:async path=>{assert.equal(path,'/synchronized/viewer-config.json');if(fail)throw Error('unavailable');return{ok:true,json:async()=>data};}};
 vm.createContext(ctx);vm.runInContext(helper,ctx);return ctx.createViewerStreamResolver();
}
test('observer metadata expands only Robo-house and preserves the original three source slots',async()=>{
 const resolve=setup(manifest),stream=await resolve(robot,old);
 assert.equal(stream.path,'robo-house');assert.deepEqual([...stream.cameras],['top','left','right','observer']);
 assert.deepEqual(old.cameras,['top','left','right']);
 const yam={path:'synchronized-hd',cameras:['top','observer','left','right']};
 assert.equal(await resolve('yam-1',yam),yam);
 assert.equal(await resolve(robot,null),null);
});
test('missing, failed and invalid manifests keep configured streams',async()=>{
 for(const bad of [null,{}, {...manifest,version:2}, {version:1,streams:{[robot]:{path:'other',cameras:['observer']}}},
  {version:1,streams:{[robot]:{path:'robo-house',cameras:['top','top']}}},
  {version:1,streams:{[robot]:{path:'robo-house',cameras:['private']}}}])assert.equal(await setup(bad)(robot,old),old);
 assert.equal(await setup(null,true)(robot,old),old);
});
