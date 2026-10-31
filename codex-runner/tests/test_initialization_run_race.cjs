const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('static/hosted.js','utf8');
const block=source.slice(source.indexOf('  function finishInitialization('),source.indexOf('  async function start() {'));
function fixture(started=false){let polls=0;const messages=[];const context=vm.createContext({pollingStarted:started,poll(){polls++;},message(...args){messages.push(args);}});vm.runInContext(block,context);return {context,messages,polls:()=>polls,finish:error=>context.finishInitialization(error)};}
test('Run during the initial read resumes one status loop without another run submission',()=>{
 const f=fixture();f.finish(Object.assign(new Error('Run attempt changed'),{stale:true}));
 assert.equal(f.polls(),1);assert.equal(f.messages.length,0);assert.equal(f.context.pollingStarted,true);
 f.finish();f.finish({stale:true});assert.equal(f.polls(),1);
});
test('actual initialization errors retain recovery feedback and do not fabricate readiness',()=>{
 const f=fixture();f.finish(new Error('Session unavailable'));
 assert.deepEqual(f.messages,[['Session unavailable',true]]);assert.equal(f.polls(),0);
});
test('an already-started loop is retained after a stale read',()=>{
 const f=fixture(true);f.finish({stale:true});assert.equal(f.polls(),0);
});
