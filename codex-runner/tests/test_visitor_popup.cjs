const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/../static/hosted.js','utf8');
const start=source.indexOf("(() => {\n  const panel = document.getElementById('visitorChatPanel');");
const popup=source.slice(start,source.indexOf('\n})();',start)+6);
function harness() {
  const callbacks={},expanded={},focus=[],events={};let storageReads=0,observe;
  const classes=()=>{const values=new Set();return {contains:key=>values.has(key),toggle(key,value){value?values.add(key):values.delete(key);}};};
  const pane={classList:classes(),append(node){node.parent=this;},scrollIntoView(){}};
  const footer={classList:classes(),append(node){node.parent=this;}};
  const panel={hidden:false,classList:classes(),focus(){focus.push('panel');}};
  const button=id=>({hidden:false,setAttribute(name,value){expanded[id]=value;},focus(){focus.push(id);},addEventListener(_,callback){callbacks[id]=callback;}});
  const nodes={visitorChatPanel:panel,openVisitorChat:button('open'),closeVisitorChat:button('close'),chatPaneTitle:{textContent:'Activity'},chatMessages:{scrollTop:0,scrollHeight:1200}};
  const choose=mode=>events['yam:conversation-mode']({detail:{mode}});
  vm.runInNewContext(popup,{document:{getElementById:id=>nodes[id],querySelector(selector){if(selector==='.watchInteraction')return pane;if(selector==='.cameraFooter')return footer;return {click(){choose(selector.match(/="(.+)"/)[1]);}};},addEventListener(name,callback){events[name]=callback;}},MutationObserver:class{constructor(callback){observe=callback;}observe(){}},localStorage:{getItem(){storageReads++;return 'true';},setItem(){}}});
  return {panel,pane,footer,nodes,expanded,focus,callbacks,choose,escape(){events.keydown({key:'Escape',preventDefault(){}});},reposition(){observe();},reads:()=>storageReads};
}
test('an older saved open drawer cannot cover the playground on a fresh load',()=>{
  const h=harness();assert.equal(h.panel.hidden,true);assert.equal(h.expanded.open,'false');assert.equal(h.reads(),0);assert.deepEqual(h.focus,[]);
});
test('camera shortcut opens the people view and Escape returns focus without losing the task mode',()=>{
  const h=harness();h.callbacks.open();assert.equal(h.panel.hidden,false);assert.equal(h.expanded.open,'true');
  assert.equal(h.panel.parent,h.pane);assert.equal(h.nodes.chatMessages.scrollTop,1200);
  h.callbacks.close();assert.equal(h.panel.hidden,true);
  h.choose('conversation');h.callbacks.open();h.escape();assert.equal(h.panel.hidden,true);assert.equal(h.expanded.open,'false');assert.equal(h.focus.at(-1),'open');
  assert.equal(h.nodes.chatPaneTitle.textContent,'Activity');
});
test('the same visitor panel follows camera expansion and returns to the conversation pane',()=>{
  const h=harness();h.footer.classList.toggle('expandedCameraFooter',true);h.callbacks.open();
  assert.equal(h.panel.parent,h.footer);assert.equal(h.panel.classList.contains('visitorChatExpanded'),true);assert.equal(h.focus.at(-1),'close');
  h.footer.classList.toggle('expandedCameraFooter',false);h.reposition();
  assert.equal(h.panel.parent,h.pane);assert.equal(h.panel.hidden,false);assert.equal(h.panel.classList.contains('visitorChatExpanded'),false);
  h.choose('reasoning');assert.equal(h.panel.hidden,true);
});
