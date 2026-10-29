const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const full=fs.readFileSync(path.join(__dirname,'../../static/hosted.js'),'utf8');
const start=full.lastIndexOf('(() => {',full.indexOf('const zeroSecondVideo'));
const source=full.slice(start).split('\n})();')[0]+'\n})();';
module.exports=function setup(initialSearch='',savedView=null){
  const nodes=new Map(),events={},requests=[],opened=[],storage=new Map(),cloudPreview={shows:[],hides:0,show(...args){this.shows.push(args)},hide(){this.hides++}},cloud={rows:[],selected:null,setRuns(rows,id){this.rows=rows;this.selected=id},select(id){this.selected=id},clearPreview(){this.preview?.(null,null)},reset(){},zoom(){},step(){},open(){}};
  const timers=new Map();let timerId=0;
  if(savedView)storage.set('yam-past-runs-view',savedView);
  const element=(tag='div')=>({tag,children:[],listeners:{},dataset:{},style:{},value:'',open:false,attributes:{},plays:0,pauses:0,
    get selectedOptions(){return this.children.filter(child=>child.selected)},
    addEventListener(name,fn){(this.listeners[name]||=[]).push(fn)},emit(name,event={}){for(const fn of this.listeners[name]||[])fn(event)},
    after(){},append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children},
    removeAttribute(name){delete this.attributes[name]},setAttribute(name,value){this.attributes[name]=value},pause(){this.pauses++},play(){this.plays++;return Promise.resolve()},load(){},matches(){return true},remove(){this.removed=true},
    showModal(){this.open=true},close(){this.open=false;this.emit('close')},focus(){this.focused=true}
  });
  const document={hidden:false,addEventListener(name,fn){events[name]=fn},getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},createElement:element,createTextNode:text=>({textContent:text})};
  const window={location:{search:initialSearch},addEventListener(name,fn){events[name]=fn},yamTaskCloud:{create(canvas,text,select,preview){cloud.preview=preview;return cloud},createPreview(root,options){cloudPreview.options=options;return cloudPreview}},yamReplayReview:{ready(){},openEpisode(id,run){opened.push({id,run})}}};
  vm.runInNewContext(source,{document,window,AbortController,URLSearchParams,encodeURIComponent,renderStepMetricsChart(){},renderRunMetrics(){},
    localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},clearTimeout(id){timers.delete(id)},setTimeout(fn){timers.set(++timerId,fn);return timerId},
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}});
  const answer=(request,runs=[],next_offset=null,total=runs.length,stale=false,models=[])=>request.resolve({ok:true,json:async()=>({runs,next_offset,total,stale,models,scores:[],cloud:{status:'ready',version:'fixed-v1'}})});
  const search=query=>{nodes.get('pastRunsQuery').value=query;nodes.get('pastRunsSearch').emit('submit',{preventDefault(){}})};
  const choose=(...values)=>{const select=nodes.get('pastRunsModel');for(const option of select.children)option.selected=values.includes(option.value);select.emit('change')};
  return{timers,nodes,events,requests,answer,search,choose,opened,storage,cloud,cloudPreview,source,document,window,flush:()=>new Promise(setImmediate)};
};
