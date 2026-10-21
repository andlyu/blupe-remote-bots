const test = require('node:test'), assert = require('node:assert/strict');
const {createPlaygroundReactions} = require('../static/reactions.js');
function harness() {
  function element() {
    const classes = new Set();
    return {children:[],textContent:'',dataset:{},listeners:{},
      classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},
      setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn},
      append(...children){for(const child of children){child.parent=this;this.children.push(child)}},
      replaceChildren(){this.children=[]},
      remove(){this.parent.children=this.parent.children.filter(c=>c!==this)},
      get firstElementChild(){return this.children[0]}};
  }
  const buttons = ['🙂','😂','😠','😢'].map((emoji,i)=>Object.assign(element(),{dataset:{reaction:emoji,label:['Smile','Laugh','Angry','Cry'][i]}}));
  const dock=element(), stage=element(), chatStage=element(), status=element(), listeners={};
  dock.querySelectorAll=()=>buttons;
  const document={hidden:false,createElement:element,addEventListener(name,fn){listeners[name]=fn},getElementById:id=>({reactionDock:dock,reactionStage:stage,chatPopupStage:chatStage,reactionStatus:status}[id])};
  const timers=new Map();let serial=0;
  const ui=createPlaygroundReactions(document,(fn,ms)=>{timers.set(++serial,{fn,ms});return serial},id=>timers.delete(id));
  return {ui,buttons,stage,chatStage,status,document,listeners,timers,expire(ms){for(const [id,t] of timers) if(t.ms<=ms){timers.delete(id);t.fn()}}};
}
const reaction=(id=1,emoji='😂',remaining_ms=5000)=>({id,emoji,remaining_ms});
test('sender and another viewer display the same event once, outside chat, then remove it',async()=>{
  const a=harness(), b=harness();
  a.ui.setAvailable(true);b.ui.setAvailable(true);
  a.ui.configure(async emoji=>({reaction:reaction(1,emoji)}));
  await a.buttons[1].listeners.click();
  assert.equal(a.stage.children[0].textContent,'😂');
  a.ui.receive([reaction()]);b.ui.receive([reaction()]);
  assert.equal(a.stage.children.length,1);assert.equal(b.stage.children.length,1);
  assert(a.buttons.every(button=>button.disabled));
  a.expire(1000);assert(a.buttons.every(button=>!button.disabled));
  a.expire(2400);b.expire(2400);
  assert.equal(a.stage.children.length,0);assert.equal(b.stage.children.length,0);
});
test('reset and stale/background events do not replay; bursts remain bounded',()=>{
  const h=harness();h.ui.reset(4);
  h.ui.receive([reaction(3),reaction(4),reaction(5,'😂',1000),reaction(6,'<script>')]);
  assert.equal(h.stage.children.length,0);
  h.document.hidden=true;h.ui.receive([reaction(7)]);h.document.hidden=false;h.ui.receive([reaction(7)]);
  assert.equal(h.stage.children.length,0);
  h.ui.receive(Array.from({length:20},(_,i)=>reaction(i+8)));
  assert.equal(h.stage.children.length,6);
  h.ui.reset(28);assert.equal(h.stage.children.length,0);assert.equal(h.timers.size,0);
});
test('failed submission reports an accessible error and permits retry',async()=>{
  const h=harness();h.ui.setAvailable(true);h.ui.configure(async()=>{throw new Error('Please wait a moment')});
  await h.buttons[0].listeners.click();
  assert.equal(h.stage.children.length,0);assert.match(h.status.textContent,/Please wait/);
  assert(h.status.classList.contains('reactionError'));
  h.expire(1000);assert.equal(h.buttons[0].disabled,false);
});
test('switching rooms ignores an in-flight send from the previous room',async()=>{
  const h=harness();let finish;
  h.ui.setAvailable(true);h.ui.configure(()=>new Promise(resolve=>{finish=resolve}));
  const click=h.buttons[0].listeners.click();h.ui.reset(0);
  finish({reaction:reaction()});await click;
  assert.equal(h.stage.children.length,0);assert.equal(h.timers.size,0);
});
const chat=(id=1,at=100)=>({id,at,name:'Sam',text:'Hello everyone!'});
test('fresh chat appears once for sender and viewers, and disappears after five seconds',()=>{
  const a=harness(), b=harness();
  for(const h of [a,b]){
    h.ui.receiveChat([],100);
    h.ui.receiveChat([chat()],101);
    h.ui.receiveChat([chat()],102);
    assert.equal(h.chatStage.children.length,1);
    assert.equal(h.chatStage.children[0].children[0].textContent,'Sam');
    assert.equal(h.chatStage.children[0].children[1].textContent,'Hello everyone!');
    h.expire(4999);assert.equal(h.chatStage.children.length,1);
    h.expire(5000);assert.equal(h.chatStage.children.length,0);
    h.ui.receiveChat([chat()],104);assert.equal(h.chatStage.children.length,0);
  }
});
test('chat history, outages, background tabs and room changes never replay old popups',()=>{
  const h=harness();
  h.ui.receiveChat([chat()],101);assert.equal(h.chatStage.children.length,0);
  h.ui.receiveChat([chat(),chat(2,101)],110);assert.equal(h.chatStage.children.length,0);
  h.ui.receiveChat([chat(3,110)],110);assert.equal(h.chatStage.children.length,1);
  h.document.hidden=true;h.listeners.visibilitychange();assert.equal(h.chatStage.children.length,0);
  h.ui.receiveChat([chat(3,110),chat(4,111)],111);
  h.document.hidden=false;h.listeners.visibilitychange();
  h.ui.receiveChat([chat(4,111)],112);assert.equal(h.chatStage.children.length,0);
  h.ui.receiveChat([chat(4,111),chat(5,112)],113);assert.equal(h.chatStage.children.length,1);
  h.ui.reset();assert.equal(h.chatStage.children.length,0);assert.equal(h.timers.size,0);
  h.ui.receiveChat([chat(1,112)],113);assert.equal(h.chatStage.children.length,0);
});
test('chat uses server time, treats markup as text, and bounds bursts independently of emoji',()=>{
  const h=harness();h.ui.receiveChat([],100);
  h.ui.receiveChat([{...chat(),name:'<img onerror=alert(1)>',text:'<script>alert(1)</script>'}],101);
  assert.equal(h.chatStage.children[0].children[0].textContent,'<img onerror=alert(1)>');
  assert.equal(h.chatStage.children[0].children[1].textContent,'<script>alert(1)</script>');
  h.ui.receiveChat(Array.from({length:10},(_,i)=>chat(i+2,101)),102);
  assert.equal(h.chatStage.children.length,3);
  h.ui.receive([reaction()]);assert.equal(h.stage.children.length,1);
  h.expire(2400);assert.equal(h.stage.children.length,0);assert.equal(h.chatStage.children.length,3);
  h.expire(5000);assert.equal(h.chatStage.children.length,0);
});
