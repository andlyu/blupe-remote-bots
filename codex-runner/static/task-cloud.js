/* Perspective projection of real persisted xyz coordinates; Canvas API references
   and MiniLM/PCA provenance are in docs/refs/task-cloud/INDEX.md. */
(() => {
  'use strict';
  const offset = id => {
    let hash = 2166136261;
    for (const char of id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
    return [0,8,16].map(shift => (((hash >>> shift) & 255)/255-.5)*.035);
  };
  function project(xyz, yaw, pitch, zoom, width, height) {
    const x = xyz[0]*Math.cos(yaw)+xyz[2]*Math.sin(yaw);
    const z = -xyz[0]*Math.sin(yaw)+xyz[2]*Math.cos(yaw);
    const y = xyz[1]*Math.cos(pitch)-z*Math.sin(pitch);
    const depth = xyz[1]*Math.sin(pitch)+z*Math.cos(pitch);
    const perspective = Math.min(width,height)*2.6*zoom/Math.max(.8,3+depth);
    return {x:width/2+x*perspective,y:height/2-y*perspective,depth};
  }
  const legacyOutcome = run => run.assessment?.eligibility === 'included' && ['Success','Failure'].includes(run.assessment.label)
    ? run.assessment.label : 'Unscored';
  const outcome = run => window.yamRunLabels?.outcome(run, run.label_source || 'human') || legacyOutcome(run);
  const regionRadius = .08;
  const validPosition = run => Array.isArray(run.xyz) && run.xyz.length === 3 && run.xyz.every(Number.isFinite);
  const distanceSquared = (a,b) => a.reduce((sum,value,i) => sum+(value-b[i])**2,0);
  function regionsFor(runs) {
    // Count in persisted 3D coordinates, before display jitter or rotation.
    // Aggregate identical tasks and use a spatial hash to bound the search.
    const groups = new Map(), buckets = new Map(), nearby = new Map();
    for (const run of runs.filter(validPosition)) {
      const key = run.xyz.join(','), state = outcome(run);
      if (!groups.has(key)) groups.set(key,{xyz:run.xyz,Success:0,Failure:0,Uncertain:0,Unscored:0});
      groups.get(key)[state]++;
    }
    const cell = xyz => xyz.map(value => Math.floor(value/regionRadius));
    for (const group of groups.values()) {
      const key = cell(group.xyz).join(',');
      if (!buckets.has(key)) buckets.set(key,[]);
      buckets.get(key).push(group);
    }
    const candidates = [];
    for (const [key,group] of groups) {
      const counts = {Success:0,Failure:0,Uncertain:0,Unscored:0}, base = cell(group.xyz);
      for (let x=-1;x<=1;x++) for (let y=-1;y<=1;y++) for (let z=-1;z<=1;z++) {
        for (const other of buckets.get([base[0]+x,base[1]+y,base[2]+z].join(',')) || []) {
          if (distanceSquared(group.xyz,other.xyz)>regionRadius**2) continue;
          for (const label of Object.keys(counts)) counts[label]+=other[label];
        }
      }
      nearby.set(key,counts);
      const total=counts.Success+counts.Failure, share=counts.Success/total;
      if (!group.Success && !group.Failure || total<5 || (share>1/3 && share<2/3)) continue;
      candidates.push({xyz:group.xyz,...counts,total,label:share>=2/3?'Success':'Failure',strength:Math.abs(counts.Success-counts.Failure)});
    }
    candidates.sort((a,b)=>b.strength-a.strength || b.total-a.total || a.xyz.join(',').localeCompare(b.xyz.join(',')));
    const regions=[];
    for (const candidate of candidates) {
      if (regions.filter(r=>r.label===candidate.label).length>=12) continue;
      if (regions.some(r=>r.label===candidate.label && distanceSquared(r.xyz,candidate.xyz)<(regionRadius*1.5)**2)) continue;
      regions.push(candidate);
    }
    return {regions,nearby};
  }
  // Three paused players at most: the active preview plus nearby/recent points.
  // Keep their buffers on pointer exit; explicit hide releases the entire cache.
  function createPreview(root, {loadRun, source, layout, canPlay = () => true, reducedMotion = () => false}) {
    const media = root.querySelector('.taskCloudPreviewMedia'), title = root.querySelector('.taskCloudPreviewTitle');
    const status = root.querySelector('.taskCloudPreviewState');
    const cache = new Map(), key = run => `${run.robot_id || ''}:${run.episode_id}`;
    let current = null, generation = 0, request = null, video = null, dispose = null, anchor = null;
    const state = (entry, message) => {if (current === entry) {status.textContent = message; position();}};
    function release(entry) {
      entry.controller?.abort();
      if (entry.video) {entry.video.pause(); entry.video.removeAttribute('src'); entry.video.load();}
      cache.delete(entry.key);
    }
    function entryFor(run) {
      const id = key(run);
      let entry = cache.get(id);
      if (entry && entry !== current && Date.now()-entry.created > 60000) {release(entry); entry = null;}
      if (!entry) entry = {key:id,run,created:Date.now(),checked:0};
      cache.delete(id); cache.set(id,entry);
      for (const candidate of cache.values()) {
        if (cache.size <= 3) break;
        if (candidate !== current && candidate !== entry) release(candidate);
      }
      return entry;
    }
    async function prepare(entry) {
      if (entry.video) return entry.detail;
      if (entry.pending) return entry.pending;
      const controller = new AbortController(); entry.controller = controller;
      entry.pending = (async () => {
        const detail = entry.run.preview?.video_url ? entry.run.preview : await loadRun(entry.run,controller.signal);
        if (controller.signal.aborted || cache.get(entry.key) !== entry) return null;
        entry.checked = Date.now(); entry.detail = detail;
        if (detail?.video_status === 'processing' || !detail?.video_url || detail.video_duration_s === 0) return detail;
        const recording = {...entry.run,...detail}, playback = source(recording);
        const clip = entry.video = document.createElement('video');
        clip.defaultMuted = clip.muted = true; clip.playsInline = true; clip.loop = true;
        clip.preload = reducedMotion() ? 'metadata' : 'auto';
        clip.setAttribute('muted',''); clip.setAttribute('playsinline','');
        clip.setAttribute('aria-hidden','true'); clip.tabIndex = -1;
        clip.addEventListener('playing', () => state(entry,'Playing muted preview · Open run for full replay'));
        clip.addEventListener('waiting', () => state(entry,'Buffering video…'));
        clip.addEventListener('error', () => {
          state(entry,'Video unavailable. Open run to retry.');
          if (cache.get(entry.key) === entry) release(entry);
        });
        clip.addEventListener('loadedmetadata', () => {if (current === entry) position();});
        clip.src = playback.url; clip.defaultPlaybackRate = clip.playbackRate = playback.rate;
        return detail;
      })();
      try {return await entry.pending;}
      finally {if (entry.controller === controller) entry.pending = null;}
    }
    function warm(runs) {
      if (!canPlay() || reducedMotion() || window.navigator?.connection?.saveData) return;
      const wanted = new Set(runs.slice(0,2).map(key));
      for (const entry of cache.values()) if (entry !== current && entry.pending && !wanted.has(entry.key)) release(entry);
      for (const run of runs.slice(0,2)) {
        const entry = entryFor(run);
        if (entry.detail?.video_status === 'processing' && Date.now()-entry.checked < 1000) continue;
        void prepare(entry).catch(() => {if (cache.get(entry.key) === entry) release(entry);});
      }
    }
    function position() {
      if (!anchor) return;
      const width = root.offsetWidth, height = root.offsetHeight;
      const x = anchor.x + 18 + width <= anchor.width - 8 ? anchor.x + 18 : anchor.x - width - 18;
      root.style.left = Math.max(8, Math.min(anchor.width-width-8, x))+'px';
      root.style.top = Math.max(8, Math.min(anchor.height-height-8, anchor.y-24))+'px';
    }
    function park() {
      generation++; request?.abort(); request = null;
      if (current && !current.video) release(current);
      current = null; anchor = null;
      if (video) {video.pause(); dispose?.();}
      video = null; dispose = null; media.replaceChildren(); root.hidden = true;
      delete root.dataset.episodeId;
    }
    function hide() {park(); for (const entry of cache.values()) release(entry);}
    async function show(run, point) {
      if (!canPlay()) {hide(); return;}
      if (!run) {park(); return;}
      if (current?.key === key(run)) {anchor = point; position(); return;}
      park(); current = entryFor(run); anchor = point;
      const entry = current;
      const version = generation;
      request = new AbortController();
      root.dataset.episodeId = run.episode_id; root.hidden = false;
      title.textContent = run.prompt; status.textContent = 'Loading video…'; position();
      try {
        let detail;
        for (let attempt = 0; attempt < 60; attempt++) {
          detail = await prepare(entry);
          if (version !== generation || !canPlay()) return;
          if (detail?.video_status !== 'processing') break;
          status.textContent = 'Preparing recorded video…'; position();
          await new Promise((resolve,reject) => {
            const signal = request.signal;
            const abort = () => {clearTimeout(timer); reject(new Error('Preview cancelled'));};
            const timer = setTimeout(() => {signal.removeEventListener('abort',abort);resolve();},1000);
            signal.addEventListener('abort',abort,{once:true});
          });
        }
        if (version !== generation || !canPlay()) return;
        if (detail?.video_status === 'processing') {
          status.textContent = 'Video is still preparing. Open run for details.'; position(); return;
        }
        if (!detail?.video_url || detail.video_duration_s === 0) {
          status.textContent = 'No preview available. Open run for details.'; return;
        }
        const recording = {...run,...detail};
        video = entry.video;
        const clip = video;
        media.append(clip); dispose = layout?.(clip, recording.camera_order, recording.video_layout);
        const state = message => {if (version === generation) {status.textContent = message; position();}};
        position();
        if (reducedMotion()) state('Preview paused for reduced motion. Open run to play.');
        else await clip.play().catch(error => state(error.name === 'NotAllowedError'
          ? 'Preview playback was blocked. Open run to play.' : 'Preview could not play. Open run to play.'));
      } catch (_) {
        if (version === generation) status.textContent = 'Video unavailable. Open run to retry.';
      }
    }
    return {show,hide,warm};
  }
  function create(canvas, focusText, onSelect, onPreview = () => {}, onWarm = () => {}) {
    const ctx = canvas.getContext('2d');
    let rows = [], points = [], yaw = -.3, pitch = .2, magnification = 1, focused = 0, selected = '', hover = null;
    let frame = null, moved = false, last = null, lastDistance = 0, hitCycle = 0, lastHits = '';
    let highlight = 'none', regionData = null;
    const regionAnalysis = () => regionData ||= regionsFor(rows);
    const visibleRegions = () => highlight === 'none' ? [] : regionAnalysis().regions.filter(r => highlight === 'both' || r.label.toLowerCase() === highlight);
    function highlightSummary() {
      if (highlight === 'none') return 'Region highlights off. Individual run colors remain visible.';
      const regions=visibleRegions(), success=regions.filter(r=>r.label==='Success').length, failure=regions.length-success;
      return `${regions.length ? `Highlighting ${success} success-heavy / ${failure} failure-heavy areas.` : 'No areas meet the highlight threshold for this selection.'} Tints need at least 5 Success/Failure labels nearby and two-thirds of one outcome. Uncertain and unlabeled runs are not counted. Areas can overlap; hover or focus a run for nearby counts.`;
    }
    const pointers = new Map();
    const schedule = () => { if (frame == null) frame = requestAnimationFrame(draw); };
    function description(run) {
      const a = run.assessment || {};
      if (window.yamRunLabels) return `${run.prompt} · ${window.yamRunLabels.describe(run, run.label_source || 'human')} · ${run.episode_id}`;
      return `${run.prompt} · ${run.model || 'Model not recorded'} · ${run.model_version || 'version unknown'} · ${outcome(run)} · Runner label: ${a.label || 'Unlabeled'} · ${a.correct || 0} correct / ${a.incorrect || 0} incorrect · ${a.eligibility || 'unlabeled'} · ${run.episode_id}`;
    }
    function focus(run) {
      focusText.textContent = run ? description(run) : 'No runs match these filters. Choose another model or clear search.';
      if (run && highlight !== 'none' && validPosition(run)) {
        const counts=regionAnalysis().nearby.get(run.xyz.join(','));
        if (counts) focusText.textContent+=` · Nearby: ${counts.Success} Success / ${counts.Failure} Failure; ${counts.Uncertain} Uncertain and ${counts.Unscored} unlabeled or excluded not counted.`;
      }
    }
    function marker(point) {
      const radius = selected === point.run.episode_id || hover === point.run.episode_id ? 7 : 4.5;
      const state = outcome(point.run), color = state === 'Success' ? '#246744' : state === 'Failure' ? '#b2352c' : state === 'Uncertain' ? '#946000' : '#607064';
      ctx.beginPath();
      ctx.arc(point.x,point.y,radius,0,Math.PI*2);
      ctx.fillStyle = state === 'Unscored' ? '#f8faf5' : color;
      ctx.strokeStyle = color;
      ctx.lineWidth = state === 'Unscored' ? 1.75 : 1;
      ctx.fill();ctx.stroke();
      if (selected === point.run.episode_id || hover === point.run.episode_id) {
        ctx.beginPath();ctx.arc(point.x,point.y,11,0,Math.PI*2);ctx.strokeStyle='#172c21';ctx.lineWidth=1.5;ctx.stroke();
      }
    }
    function draw() {
      frame = null;
      const width = canvas.clientWidth || 1000, height = canvas.clientHeight || 540, dpr = Math.min(window.devicePixelRatio || 1,2);
      if (canvas.width !== Math.round(width*dpr) || canvas.height !== Math.round(height*dpr)) {
        canvas.width = Math.round(width*dpr);canvas.height = Math.round(height*dpr);
      }
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
      ctx.fillStyle='#f8faf5';ctx.fillRect(0,0,width,height);
      const regionPoints=visibleRegions().map(region=>({...region,...project(region.xyz,yaw,pitch,magnification,width,height)})).sort((a,b)=>b.depth-a.depth);
      for (const region of regionPoints) {
        const radius=Math.min(width,height)*2.6*magnification*regionRadius/Math.max(.8,3+region.depth);
        if (region.x+radius<0 || region.x-radius>width || region.y+radius<0 || region.y-radius>height) continue;
        const rgb=region.label==='Success'?'36,103,68':'178,53,44';
        const field=ctx.createRadialGradient(region.x,region.y,0,region.x,region.y,radius*1.4);
        field.addColorStop(0,`rgba(${rgb},.30)`);field.addColorStop(.55,`rgba(${rgb},.15)`);field.addColorStop(1,`rgba(${rgb},0)`);
        ctx.fillStyle=field;ctx.beginPath();ctx.arc(region.x,region.y,radius*1.4,0,Math.PI*2);ctx.fill();
      }
      // Rotation reference: three real perspective axes, with no outcome meaning.
      const origin=project([0,0,0],yaw,pitch,magnification,width,height);
      for (const [i,name] of ['x','y','z'].entries()) {
        const axis=[0,0,0];axis[i]=.65;
        const end=project(axis,yaw,pitch,magnification,width,height);
        ctx.beginPath();ctx.moveTo(origin.x,origin.y);ctx.lineTo(end.x,end.y);ctx.strokeStyle='#cbd5ca';ctx.lineWidth=1;ctx.stroke();
        ctx.fillStyle='#536155';ctx.font='12px system-ui';ctx.fillText(name,end.x+5,end.y);
      }
      points = rows.filter(validPosition).map(run => {
        const delta=offset(run.episode_id), xyz=run.xyz.map((value,i)=>value+delta[i]);
        return {...project(xyz,yaw,pitch,magnification,width,height),run};
      }).sort((a,b)=>b.depth-a.depth);
      for (const point of points) if (point.x>-15 && point.x<width+15 && point.y>-15 && point.y<height+15) marker(point);
      const labels = points.filter(p=>p.run.episode_id===hover || p.run.episode_id===selected || p.run===rows[focused]);
      if (magnification>1.8) labels.push(...points.filter(p=>!labels.includes(p)).slice().reverse());
      const boxes=[];
      ctx.font='600 12px system-ui';
      const rankedRegions=regionPoints.slice().sort((a,b)=>b.strength-a.strength);
      const successes=rankedRegions.filter(r=>r.label==='Success'), failures=rankedRegions.filter(r=>r.label==='Failure');
      const labelRegions=highlight==='both'
        ? Array.from({length:3},(_,i)=>[successes[i],failures[i]]).flat().filter(Boolean)
        : rankedRegions.slice(0,6);
      for (const region of labelRegions) {
        if (region.x<0 || region.x>width || region.y<0 || region.y>height) continue;
        const text=`${region.label}: ${region[region.label]}/${region.total}`, w=ctx.measureText(text).width+14;
        const x=Math.max(4,Math.min(width-w-4,region.x-w/2)), y=Math.max(4,Math.min(height-28,region.y-42));
        if (boxes.some(b=>x<b.x+b.w+8 && x+w+8>b.x && y<b.y+32 && y+32>b.y)) continue;
        boxes.push({x,y,w});ctx.fillStyle='#f8faf5';ctx.fillRect(x,y,w,24);
        ctx.strokeStyle=region.label==='Success'?'#246744':'#b2352c';ctx.lineWidth=1;ctx.strokeRect(x,y,w,24);
        ctx.fillStyle=ctx.strokeStyle;ctx.fillText(text,x+7,y+16);
      }
      ctx.font='13px system-ui';
      for (const point of labels) {
        if (boxes.length>=14) break;
        const text=point.run.prompt.length>64?point.run.prompt.slice(0,61)+'…':point.run.prompt;
        const length=Math.min(ctx.measureText(text).width+12,width-12);
        const x=Math.max(4,Math.min(width-length-4,point.x+12)),y=Math.max(4,Math.min(height-27,point.y-25));
        if(boxes.some(b=>x<b.x+b.w && x+length>b.x && y<b.y+25 && y+25>b.y)) continue;
        boxes.push({x,y,w:length});ctx.fillStyle='#f8faf5';ctx.fillRect(x,y,length,24);ctx.fillStyle='#172c21';ctx.fillText(text,x+6,y+17,length-12);
      }
      canvas.dataset.renderedPoints=String(points.length);
      canvas.dataset.cloudCamera=[yaw,pitch,magnification].join(',');
      canvas.dataset.highlightRegions=String(regionPoints.length);
      canvas.dataset.regionMode=highlight;
    }
    function hit(event) {
      const rect=canvas.getBoundingClientRect(), x=event.clientX-rect.left,y=event.clientY-rect.top;
      return points.filter(p=>Math.hypot(p.x-x,p.y-y)<13).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y));
    }
    function preview(point) {onPreview(point?.run || null, point ? {x:point.x,y:point.y,width:canvas.clientWidth,height:canvas.clientHeight} : null);}
    function clearPreview() {hover=null;preview(null);}
    function previewFocused() {const point=points.find(p=>p.run===rows[focused]);hover=point?.run.episode_id;onWarm([rows[focused],rows[(focused+1)%rows.length]].filter(Boolean));preview(point);schedule();}
    function zoom(factor) {clearPreview();magnification=Math.max(.4,Math.min(8,magnification*factor));schedule();}
    function reset() {clearPreview();yaw=-.3;pitch=.2;magnification=1;schedule();}
    function open() {if(rows[focused]) {clearPreview();selected=rows[focused].episode_id;focus(rows[focused]);onSelect(rows[focused]);schedule();}}
    function step(delta) {if(rows.length) {focused=(focused+delta+rows.length)%rows.length;focus(rows[focused]);previewFocused();}}
    canvas.addEventListener('pointerdown',event=>{
      clearPreview();
      pointers.set(event.pointerId,[event.clientX,event.clientY]);canvas.setPointerCapture(event.pointerId);
      last=[event.clientX,event.clientY];moved=false;
      if(pointers.size===2) {const [a,b]=[...pointers.values()];lastDistance=Math.hypot(a[0]-b[0],a[1]-b[1]);}
    });
    canvas.addEventListener('pointermove',event=>{
      if(pointers.has(event.pointerId)) {
        pointers.set(event.pointerId,[event.clientX,event.clientY]);
        if(pointers.size===2) {
          const [a,b]=[...pointers.values()],distance=Math.hypot(a[0]-b[0],a[1]-b[1]);
          if(lastDistance>0) zoom(distance/lastDistance);lastDistance=distance;moved=true;
        } else if(last) {
          const dx=event.clientX-last[0],dy=event.clientY-last[1];
          if(Math.abs(dx)+Math.abs(dy)>2) moved=true;
          yaw+=dx*.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+dy*.008));last=[event.clientX,event.clientY];schedule();
        }
      } else {
        if (event.pointerType !== 'touch') {
          const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
          onWarm(points.map(p=>({point:p,distance:Math.hypot(p.x-x,p.y-y)})).filter(p=>p.distance<100)
            .sort((a,b)=>a.distance-b.distance).slice(0,2).map(p=>p.point.run));
        }
        const point=hit(event)[0];
        if(hover!==point?.run.episode_id) {hover=point?.run.episode_id;focus(point?.run || rows[focused]);canvas.style.cursor=point?'pointer':'grab';preview(event.pointerType === 'touch' ? null : point);schedule();}
      }
    });
    canvas.addEventListener('pointerup',event=>{
      const dragged=moved || pointers.size>1;pointers.delete(event.pointerId);last=null;
      if(!dragged) {
        const hits=hit(event),signature=hits.map(p=>p.run.episode_id).join(',');
        hitCycle=signature===lastHits?(hitCycle+1)%Math.max(1,hits.length):0;lastHits=signature;
        if(hits.length) {focused=rows.indexOf(hits[hitCycle].run);open();}
      }
    });
    canvas.addEventListener('pointercancel',()=>{pointers.clear();last=null;clearPreview();});
    canvas.addEventListener('pointerleave',()=>{clearPreview();focus(rows[focused]);schedule();});
    canvas.addEventListener('focus',previewFocused);
    canvas.addEventListener('blur',clearPreview);
    canvas.addEventListener('wheel',event=>{event.preventDefault();zoom(Math.exp(-event.deltaY*.001));},{passive:false});
    canvas.addEventListener('keydown',event=>{
      const key=event.key;
      if(key==='Escape') {clearPreview();schedule();return;}
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Home','[',']','Enter'].includes(key)) return;
      event.preventDefault();
      if(key.startsWith('Arrow')) clearPreview();
      if(key==='ArrowLeft') yaw-=.12;if(key==='ArrowRight') yaw+=.12;
      if(key==='ArrowUp') pitch-=.12;if(key==='ArrowDown') pitch+=.12;
      if(key==='+' || key==='=') zoom(1.2);if(key==='-') zoom(1/1.2);
      if(key==='Home') reset();if(key==='[') step(-1);if(key===']') step(1);if(key==='Enter') open();schedule();
    });
    if(typeof ResizeObserver!=='undefined') new ResizeObserver(()=>{clearPreview();schedule();}).observe(canvas);
    return {setRuns(next,id) {clearPreview();rows=next;regionData=null;selected=rows.some(run=>run.episode_id===id) ? id : '';focused=Math.max(0,rows.findIndex(run=>run.episode_id===selected));focus(rows[focused]);schedule();},
      setHighlight(mode) {highlight=['both','success','failure'].includes(mode)?mode:'none';focus(rows[focused]);schedule();},highlightSummary,
      select(id) {selected=id;schedule();},clearPreview,reset,zoom,step,open};
  }
  window.yamTaskCloud={create,createPreview,project,offset,outcome,regionsFor};
})();
