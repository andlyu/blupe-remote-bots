const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),test=require('node:test');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.hidden=false;this.disabled=false;this.events={};this.value='';}
 append(...children){for(const c of children){c.parent=this;this.children.push(c);}}
 replaceChildren(...children){this.children=[];this.append(...children);}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,fn){this.events[name]=fn;}
 click(){this.events.click?.();}
 focus(){}
 after(node){this.afterNode=node;}
 remove(){this.parent.children=this.parent.children.filter(c=>c!==this);}
 querySelectorAll(selector){return this.children.flatMap(c=>[...(selector.split(',').includes(c.tagName)?[c]:[]),...c.querySelectorAll(selector)]);}
 querySelector(selector){return this.querySelectorAll(selector)[0];}
}
function setup(){const prompt=new Element('textarea'),row=new Element('row');prompt.value='First task';const ctx=vm.createContext({document:{createElement:tag=>new Element(tag)}});vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../static/hosted.js'),'utf8').split('(() => {')[0],ctx);const control=ctx.createPromptBatchControl(id=>id==='prompt'?prompt:{querySelector:()=>row});return{control,box:row.afterNode};}
const batch=status=>({phase:'running',current:1,total:3,jobs:[{prompt:'First task',status},{prompt:'Second task',status:'pending'},{prompt:'Third task',status:'pending'}]});
test('active batch collapses editors while retaining drafts and restores after completion',()=>{const{control,box}=setup();const[editor,add,note]=box.children;add.click();add.click();editor.querySelectorAll('textarea').forEach((x,i)=>x.value=`Draft ${i+2}`);control.busy(true);assert.equal(editor.hidden,true);assert.equal(add.hidden,true);assert.equal(note.hidden,true);assert.equal(editor.querySelectorAll('textarea').every(x=>x.disabled),true);control.busy(false);assert.equal(editor.hidden,false);assert.equal(add.hidden,false);assert.equal(note.hidden,false);assert.deepEqual(Array.from(control.prompts()),['First task','Draft 2','Draft 3']);});
test('batch summary reflects current run and preserves expanded prompt list across updates',()=>{const{control,box}=setup();const status=box.children[3];control.observe(batch('running'));assert.equal(status.children[0].textContent,'Prompt 1 of 3 · Running');const details=status.querySelector('details');assert.equal(details.open,false);assert.equal(details.children[0].textContent,'View 3 prompts');assert.equal(details.querySelectorAll('li').length,3);details.open=true;control.observe(batch('preparing'));assert.equal(status.children[0].textContent,'Prompt 1 of 3 · Preparing');assert.equal(status.querySelector('details').open,true);control.observe({...batch('running'),phase:'stopping'});assert.equal(status.children[0].textContent,'Prompt 1 of 3 · Stopping');control.observe(null);assert.equal(status.children.length,0);});
