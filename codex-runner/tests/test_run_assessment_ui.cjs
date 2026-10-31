const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(){
 const nodes=new Map(),requests=[],events=[];
 const element=()=>({hidden:false,disabled:false,dataset:{},children:[],listeners:{},attributes:{},
  addEventListener(name,fn){this.listeners[name]=fn},setAttribute(name,value){this.attributes[name]=value},
  querySelectorAll(){return this.children},replaceChildren(...children){this.children=children},closest(){return this}});
 const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 for(const id of ['liveAssessmentControls','replayAssessmentControls'])node(id).children=['','Failure','Success'].map(label=>Object.assign(element(),{dataset:{label}}));
 node('replayVoteControls').children=['1','-1',''].map(vote=>Object.assign(element(),{dataset:{vote}}));
 const window={dispatchEvent:event=>events.push(event)};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/run-assessments.js'),'utf8'),{
  window,document:{getElementById:node,createElement:element},CustomEvent:class{constructor(type){this.type=type}},
  fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}});
 const answer=(request,data,ok=true)=>request.resolve({ok,json:async()=>data}),flush=()=>new Promise(setImmediate);
 const data={revision:0,label:null,correct:0,incorrect:0,can_edit:true,can_vote:false,eligibility:'provisional',history:[]};
 return{node,requests,events,window,answer,flush,data};
}
test('controls stay visible during running and runner can save without Stop; later replay edits stay enabled',async()=>{
 const c=setup(),api=c.window.yamRunAssessment;
 api.observe({session_id:'own',episode_id:'ep_own',status:'running',task:'Lift the bottle'},'yam-1','csrf');
 assert.equal(c.node('liveAssessmentTask').textContent,'Lift the bottle');
 assert.equal(c.node('liveAssessment').hidden,false);c.answer(c.requests[0],c.data);await c.flush();
 const button=c.node('liveAssessmentControls').children[2];assert.equal(button.disabled,false);
 c.node('liveAssessmentControls').listeners.click({target:button});
 const write=c.requests[1],payload=JSON.parse(write.options.body);
 assert.deepEqual(payload,{episode_id:'ep_own',operation:'assess',label:'Success',revision:0});
 assert.equal(write.options.headers['X-YAM-Runner-Token'],'csrf');
 api.showReplay({episode_id:'ep_own'});assert.equal(c.requests.length,2,'Replay read must not race an assessment mutation');
 c.answer(write,{...c.data,revision:1,label:'Success'});await c.flush();
 assert.equal(button.attributes['aria-pressed'],'true');assert.equal(c.events[0].type,'yam-assessment-changed');
 api.observe({session_id:'own',episode_id:'ep_own',status:'stopped'},'yam-1','csrf');
 assert.equal(c.node('liveAssessmentTask').textContent,'Lift the bottle','ending metadata must retain the task tied to this assessment');
 c.answer(c.requests.at(-1),{...c.data,revision:1,label:'Success',eligibility:'included'});await c.flush();
 assert.equal(c.node('replayAssessmentControls').hidden,false);assert.equal(c.node('replayVoteControls').hidden,true);
 assert.match(c.node('replayAssessmentSummary').textContent,/Success.*Included in score/);
});
test('review buttons identify correctness, send revision and support vote removal',async()=>{
 const c=setup(),api=c.window.yamRunAssessment;api.observe({status:'idle'},'yam-1','reviewer');api.showReplay({episode_id:'ep_other'});
 c.answer(c.requests[0],{...c.data,revision:3,label:'Failure',can_edit:false,can_vote:true,eligibility:'included',my_vote:1});await c.flush();
 assert.equal(c.node('replayVoteControls').hidden,false);assert.equal(c.node('replayAssessmentControls').hidden,true);
 c.node('replayVoteControls').listeners.click({target:c.node('replayVoteControls').children[2]});
 assert.deepEqual(JSON.parse(c.requests[1].options.body),{episode_id:'ep_other',operation:'vote',vote:null,revision:3});
 c.answer(c.requests[1],{...c.data,revision:3,label:'Failure',can_edit:false,can_vote:true,eligibility:'included',my_vote:null});await c.flush();
 assert.equal(c.node('replayVoteControls').children[2].disabled,true);
});
