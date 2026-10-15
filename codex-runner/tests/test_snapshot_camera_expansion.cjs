const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/../static/hosted.js','utf8');
function harness() {
  let focused;
  class Node {
    constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.listeners={};this.classList={add(){},remove(){}};}
    get isConnected(){return this===body || !!this.parentElement?.isConnected;}
    append(...nodes){nodes.forEach(n=>{n.remove();n.parentElement=this;this.children.push(n);});}
    remove(){if(this.parentElement)this.parentElement.children.splice(this.parentElement.children.indexOf(this),1);this.parentElement=null;}
    before(n){n.parentElement=this.parentElement;this.parentElement.children.splice(this.parentElement.children.indexOf(this),0,n);}
    replaceWith(n){this.before(n);this.remove();}
    closest(selector){return selector!=='.cameraFooter' && this.tag==='figure'?this:this.parentElement?.closest(selector);}
    querySelector(){return this.children.flatMap(n=>[n,...n.children]).find(n=>n.tag==='button');}
    setAttribute(k,v){this.attrs[k]=v;} getAttribute(k){return this.attrs[k];}
    addEventListener(k,f){this.listeners[k]=f;} fire(k,event={}){return this.listeners[k]?.({target:this,...event});}
    focus(){focused=this;} showModal(){this.open=true;} close(){this.open=false;this.fire('close');}
  }
  const body=new Node('body'),grid=new Node('section'),panel=new Node('figure'),picture=new Node('div'),image=new Node('img');
  panel.dataset.cameraRole='left';picture.append(image);panel.append(picture);grid.append(panel);body.append(grid);
  const document={body,createElement:tag=>new Node(tag),createComment:()=>new Node('comment')};
  const a=source.indexOf('  function cameraExpansion('),b=source.indexOf('  function synchronizedPanels(');
  const c=source.indexOf('  function snapshotCameraExpansion('),d=source.indexOf('  function selectedCameras(',c);
  vm.runInNewContext(source.slice(a,b)+source.slice(c,d)+'\nsnapshotCameraExpansion(image);',{document,image,window:{matchMedia:()=>({matches:true})}});
  return {body,grid,panel,image,button:picture.children.find(n=>n.tag==='button'),get dialog(){return body.children.find(n=>n.tag==='dialog');},get focused(){return focused;}};
}
test('still-image feeds get a named expand button and keyboard-operable image',()=>{
  const h=harness();assert.equal(h.button.attrs['aria-label'],'Expand left camera');
  assert.equal(h.image.attrs.role,'button');assert.equal(h.image.tabIndex,0);
  assert.equal(h.image.dataset.camera,'left');assert.equal(typeof h.image.yamStop,'function');
});
test('expanding a still feed preserves the live image and restores it and focus on close',async()=>{
  const h=harness();await h.panel.fire('click',{target:h.button});
  assert(h.dialog.open);assert.equal(h.panel.parentElement,h.dialog);
  h.image.src='next-frame.jpg';h.dialog.children[0].fire('click');
  assert.equal(h.panel.parentElement,h.grid);assert.equal(h.image.src,'next-frame.jpg');assert.equal(h.focused,h.button);
});
test('switching robots closes an expanded still feed before rebuilding the grid',async()=>{
  const h=harness();await h.panel.fire('click');h.image.yamStop();
  assert.equal(h.dialog,undefined);assert.equal(h.panel.parentElement,h.grid);
  await h.panel.fire('click');assert.equal(h.dialog,undefined);
});
