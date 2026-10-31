const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
test('live assessment moves beneath its task with readable labels while preserving existing button permissions and handlers',()=>{
 const text=fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
 const source=text.slice(text.indexOf('/* Contextual run assessment placement.'));
 const classes=new Set(),statusClasses=new Set(['visuallyHidden']),nodes=new Map();
 const buttons=['','Failure','Success'].map(label=>({dataset:{label},disabled:true,listener:()=>{},setAttribute(name,value){this[name]=value}}));
 const originalHandlers=buttons.map(button=>button.listener);
 const assessment={hidden:true,classList:{add:value=>classes.add(value)},setAttribute(name,value){this[name]=value},prepend(node){nodes.set(node.id,node)}};
 const prompt={after(node){this.next=node}},panel={append(node){this.footer=node}},controls={querySelectorAll:()=>buttons};
 nodes.set('liveAssessment',assessment);nodes.set('liveAssessmentControls',controls);nodes.set('sidePrompt',{closest:selector=>selector==='.watchInteraction'?panel:prompt});
 for(const id of ['liveAssessmentStatus','assessmentWindow'])nodes.set(id,{classList:{remove:value=>statusClasses.delete(value),add:value=>statusClasses.add(value)}});
 const reaction={unchanged:true};nodes.set('reactionDock',reaction);
 vm.runInNewContext(source,{document:{getElementById:id=>nodes.get(id),createElement:()=>({})}});
 assert.equal(panel.footer,assessment);assert.ok(classes.has('runAssessmentContext'));assert.equal(assessment.hidden,true);
 assert.deepEqual(buttons.map(button=>button.textContent),['Neutral','Failure','Success']);assert.deepEqual(buttons.map(button=>button.dataset.label),['','Failure','Success']);
 for(let i=0;i<buttons.length;i++){assert.equal(buttons[i].disabled,true);assert.equal(buttons[i].listener,originalHandlers[i]);assert.match(buttons[i]['aria-label'],/Mark this run as/)}
 assert.equal(nodes.get('liveAssessmentTitle').textContent,'Your run result');assert.ok(!statusClasses.has('visuallyHidden'));assert.equal(nodes.get('reactionDock'),reaction);
});
