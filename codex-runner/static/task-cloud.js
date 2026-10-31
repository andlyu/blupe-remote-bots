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
  const runKey = run => `${run.robot_id || ''}:${run.episode_id}`;
  function medianPrompt(runs) {
    const mapped=runs.filter(validPosition);
    if (!mapped.length) return '';
    const median=[0,1,2].map(axis=>{
      const values=mapped.map(run=>run.xyz[axis]).sort((a,b)=>a-b), middle=Math.floor(values.length/2);
      return values.length%2 ? values[middle] : (values[middle-1]+values[middle])/2;
    });
    return mapped.filter(run=>typeof run.prompt==='string' && run.prompt.trim())
      .sort((a,b)=>distanceSquared(a.xyz,median)-distanceSquared(b.xyz,median) || runKey(a).localeCompare(runKey(b)) || a.prompt.localeCompare(b.prompt))[0]?.prompt.trim() || '';
  }
  function summarizeArea(runs) {
    const counts={Success:0,Failure:0,Uncertain:0,Unscored:0};
    for(const run of runs)counts[outcome(run)]++;
    const scored=counts.Success+counts.Failure;
    return {...counts,total:runs.length,scored,successRate:scored ? counts.Success/scored : null,medianPrompt:medianPrompt(runs)};
  }
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
    for (const region of regions) {
      const matching=runs.filter(run=>validPosition(run) && outcome(run)===region.label && distanceSquared(region.xyz,run.xyz)<=regionRadius**2);
      region.representativePrompt=medianPrompt(matching);
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
  function create(canvas, focusText, onSelect, onPreview = () => {}, onWarm = () => {}, onAreaChange = () => {}) {
    const ctx = canvas.getContext('2d');
    let rows = [], points = [], yaw = -.3, pitch = .2, magnification = 1, focused = 0, selected = '', hover = null;
    let frame = null, moved = false, last = null, lastDistance = 0, hitCycle = 0, lastHits = '';
    let highlight = 'none', regionData = null;
    let areaMode=false, areaApplied=false, areaKeys=new Set(), areaBounds=null, brush=null, areaStats=summarizeArea([]), areaRobot;
    const notifyArea = () => onAreaChange({...areaStats,active:areaMode,hasSelection:areaApplied,drawing:!!brush});
    const refreshArea = () => {areaStats=summarizeArea(rows.filter(run=>areaKeys.has(runKey(run))));notifyArea();};
    function setAreaSelection(enabled) {
      areaMode=!!enabled;brush=null;pointers.clear();last=null;moved=true;clearPreview();
      canvas.style.cursor=areaMode?'crosshair':'grab';notifyArea();schedule();
    }
    function clearArea() {areaApplied=false;areaKeys.clear();areaBounds=brush=null;refreshArea();schedule();}
    function dropAreaBox() {areaBounds=brush=null;notifyArea();}
    const canvasPoint = event => {
      const rect=canvas.getBoundingClientRect();
      return [Math.max(0,Math.min(canvas.clientWidth,event.clientX-rect.left)),Math.max(0,Math.min(canvas.clientHeight,event.clientY-rect.top))];
    };
    function applyBrush() {
      if(!brush)return;
      const [a,b]=brush, width=canvas.clientWidth,height=canvas.clientHeight;
      let x=Math.min(a[0],b[0]),y=Math.min(a[1],b[1]),right=Math.max(a[0],b[0]),bottom=Math.max(a[1],b[1]);
      if(right-x<4 && bottom-y<4){x=Math.max(0,x-6);y=Math.max(0,y-6);right=Math.min(width,right+6);bottom=Math.min(height,bottom+6);}
      areaBounds={x,y,w:right-x,h:bottom-y};areaApplied=true;
      areaKeys=new Set(points.filter(point=>point.x>=x && point.x<=right && point.y>=y && point.y<=bottom).map(point=>runKey(point.run)));
      brush=null;refreshArea();schedule();
    }
    const regionAnalysis = () => regionData ||= regionsFor(rows);
    const visibleRegions = () => highlight === 'none' ? [] : regionAnalysis().regions.filter(r => highlight === 'both' || r.label.toLowerCase() === highlight);
    function highlightSummary() {
      if (highlight === 'none') return 'Region highlights off. Individual run colors remain visible.';
      const regions=visibleRegions(), success=regions.filter(r=>r.label==='Success').length, failure=regions.length-success;
      return `${regions.length ? `Highlighting ${success} success-heavy / ${failure} failure-heavy areas.` : 'No areas meet the highlight threshold for this selection.'} Tints need at least 5 Success/Failure labels nearby and two-thirds of one outcome. Uncertain and unlabeled runs are not counted. Areas can overlap; hover or focus a run for nearby counts. Area labels include a median task prompt.`;
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
        const region=visibleRegions().filter(region=>region.representativePrompt && distanceSquared(region.xyz,run.xyz)<=regionRadius**2)
          .sort((a,b)=>distanceSquared(a.xyz,run.xyz)-distanceSquared(b.xyz,run.xyz))[0];
        if(region)focusText.textContent+=` · Median ${region.label.toLowerCase()} prompt: ${region.representativePrompt}`;
      }
    }
    function marker(point) {
      ctx.globalAlpha=areaApplied && !areaKeys.has(runKey(point.run)) ? .22 : 1;
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
      ctx.globalAlpha=1;
    }
    function draw() {
      frame = null;
      const width = canvas.clientWidth || 1000, height = canvas.clientHeight || 540, dpr = Math.min(window.devicePixelRatio || 1,2);
      if (canvas.width !== Math.round(width*dpr) || canvas.height !== Math.round(height*dpr)) {
        canvas.width = Math.round(width*dpr);canvas.height = Math.round(height*dpr);
      }
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
      ctx.fillStyle='#f8faf5';ctx.fillRect(0,0,width,height);
      const box=brush ? {x:Math.min(brush[0][0],brush[1][0]),y:Math.min(brush[0][1],brush[1][1]),w:Math.abs(brush[1][0]-brush[0][0]),h:Math.abs(brush[1][1]-brush[0][1])} : areaBounds;
      if(box){ctx.fillStyle='rgba(23,44,33,.07)';ctx.fillRect(box.x,box.y,box.w,box.h);}
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
        ? Array.from({length:width<600?2:3},(_,i)=>[successes[i],failures[i]]).flat().filter(Boolean)
        : rankedRegions.slice(0,6);
      for (const region of labelRegions) {
        if (region.x<0 || region.x>width || region.y<0 || region.y>height) continue;
        ctx.font='600 12px system-ui';
        const text=`${region.label}: ${region[region.label]}/${region.total}`, countWidth=ctx.measureText(text).width;
        const lines=[], maxTextWidth=Math.min(210,width-30);
        if (region.representativePrompt) {
          ctx.font='12px system-ui';
          for (const word of region.representativePrompt.split(/\s+/)) {
            const index=Math.max(0,lines.length-1), next=lines[index] ? lines[index]+' '+word : word;
            if (ctx.measureText(next).width<=maxTextWidth || !lines[index]) lines[index]=next;
            else lines.push(word);
          }
          if(lines.length>2)lines.splice(1,lines.length-1,lines.slice(1).join(' '));
          for(let i=0;i<lines.length;i++)if(ctx.measureText(lines[i]).width>maxTextWidth){while(lines[i].length && ctx.measureText(lines[i]+'…').width>maxTextWidth)lines[i]=lines[i].slice(0,-1);lines[i]+='…';}
        }
        const w=Math.max(countWidth,...lines.map(line=>ctx.measureText(line).width))+14, h=24+lines.length*16;
        const x=Math.max(4,Math.min(width-w-4,region.x-w/2));
        const positions=[0,1,-1,2,-2,3,-3].map(offset=>({offset,y:Math.max(4,Math.min(height-h-4,region.y-42+offset*(h+10)))}));
        const position=positions.find(({y})=>!boxes.some(b=>x<b.x+b.w+8 && x+w+8>b.x && y<b.y+b.h+8 && y+h+8>b.y));
        if(!position)continue;
        const y=position.y;
        if(position.offset){ctx.beginPath();ctx.moveTo(Math.max(x,Math.min(x+w,region.x)),Math.max(y,Math.min(y+h,region.y)));ctx.lineTo(region.x,region.y);ctx.strokeStyle=region.label==='Success'?'#246744':'#b2352c';ctx.lineWidth=1;ctx.stroke();}
        boxes.push({x,y,w,h});ctx.fillStyle='#f8faf5';ctx.fillRect(x,y,w,h);
        ctx.strokeStyle=region.label==='Success'?'#246744':'#b2352c';ctx.lineWidth=1;ctx.strokeRect(x,y,w,h);
        ctx.font='600 12px system-ui';
        ctx.fillStyle=ctx.strokeStyle;ctx.fillText(text,x+7,y+16);
        ctx.font='12px system-ui';ctx.fillStyle='#172c21';
        lines.forEach((line,index)=>ctx.fillText(line,x+7,y+32+index*16));
      }
      ctx.font='13px system-ui';
      for (const point of labels) {
        if (boxes.length>=14) break;
        const text=point.run.prompt.length>64?point.run.prompt.slice(0,61)+'…':point.run.prompt;
        const length=Math.min(ctx.measureText(text).width+12,width-12);
        const x=Math.max(4,Math.min(width-length-4,point.x+12)),y=Math.max(4,Math.min(height-27,point.y-25));
        if(boxes.some(b=>x<b.x+b.w && x+length>b.x && y<b.y+b.h && y+24>b.y)) continue;
        boxes.push({x,y,w:length,h:24});ctx.fillStyle='#f8faf5';ctx.fillRect(x,y,length,24);ctx.fillStyle='#172c21';ctx.fillText(text,x+6,y+17,length-12);
      }
      if(box){ctx.strokeStyle='#172c21';ctx.lineWidth=2;ctx.setLineDash(brush?[5,4]:[]);ctx.strokeRect(box.x,box.y,box.w,box.h);ctx.setLineDash([]);}
      canvas.dataset.renderedPoints=String(points.length);
      canvas.dataset.cloudCamera=[yaw,pitch,magnification].join(',');
      canvas.dataset.highlightRegions=String(regionPoints.length);
      canvas.dataset.regionMode=highlight;
      canvas.dataset.areaSelected=String(areaKeys.size);
    }
    function hit(event) {
      const rect=canvas.getBoundingClientRect(), x=event.clientX-rect.left,y=event.clientY-rect.top;
      return points.filter(p=>Math.hypot(p.x-x,p.y-y)<13).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y));
    }
    function preview(point) {onPreview(point?.run || null, point ? {x:point.x,y:point.y,width:canvas.clientWidth,height:canvas.clientHeight} : null);}
    function clearPreview() {hover=null;preview(null);}
    function previewFocused() {if(areaMode)return;const point=points.find(p=>p.run===rows[focused]);hover=point?.run.episode_id;onWarm([rows[focused],rows[(focused+1)%rows.length]].filter(Boolean));preview(point);schedule();}
    function zoom(factor) {clearPreview();dropAreaBox();magnification=Math.max(.4,Math.min(8,magnification*factor));schedule();}
    function reset() {clearPreview();dropAreaBox();yaw=-.3;pitch=.2;magnification=1;schedule();}
    function open() {if(rows[focused]) {clearPreview();selected=rows[focused].episode_id;focus(rows[focused]);onSelect(rows[focused]);schedule();}}
    function step(delta) {if(rows.length) {focused=(focused+delta+rows.length)%rows.length;focus(rows[focused]);previewFocused();}}
    canvas.addEventListener('pointerdown',event=>{
      clearPreview();
      pointers.set(event.pointerId,[event.clientX,event.clientY]);canvas.setPointerCapture(event.pointerId);
      last=[event.clientX,event.clientY];moved=false;
      if(pointers.size===2) {dropAreaBox();const [a,b]=[...pointers.values()];lastDistance=Math.hypot(a[0]-b[0],a[1]-b[1]);moved=true;}
      else if(areaMode){const point=canvasPoint(event);brush=[point,point];last=null;notifyArea();schedule();}
    });
    canvas.addEventListener('pointermove',event=>{
      if(pointers.has(event.pointerId)) {
        pointers.set(event.pointerId,[event.clientX,event.clientY]);
        if(brush && pointers.size===1){brush[1]=canvasPoint(event);moved=true;schedule();}
        else if(pointers.size===2) {
          const [a,b]=[...pointers.values()],distance=Math.hypot(a[0]-b[0],a[1]-b[1]);
          if(lastDistance>0) zoom(distance/lastDistance);lastDistance=distance;moved=true;
        } else if(last) {
          const dx=event.clientX-last[0],dy=event.clientY-last[1];
          if(Math.abs(dx)+Math.abs(dy)>2) moved=true;
          dropAreaBox();yaw+=dx*.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+dy*.008));last=[event.clientX,event.clientY];schedule();
        }
      } else {
        if(areaMode){canvas.style.cursor='crosshair';return;}
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
      if(!pointers.has(event.pointerId))return;
      if(brush){brush[1]=canvasPoint(event);pointers.delete(event.pointerId);last=null;moved=true;applyBrush();return;}
      const dragged=moved || pointers.size>1;pointers.delete(event.pointerId);last=null;
      if(!dragged) {
        const hits=hit(event),signature=hits.map(p=>p.run.episode_id).join(',');
        hitCycle=signature===lastHits?(hitCycle+1)%Math.max(1,hits.length):0;lastHits=signature;
        if(hits.length) {focused=rows.indexOf(hits[hitCycle].run);open();}
      }
    });
    canvas.addEventListener('pointercancel',()=>{pointers.clear();last=null;brush=null;clearPreview();notifyArea();schedule();});
    canvas.addEventListener('pointerleave',()=>{clearPreview();focus(rows[focused]);schedule();});
    canvas.addEventListener('focus',previewFocused);
    canvas.addEventListener('blur',clearPreview);
    canvas.addEventListener('wheel',event=>{event.preventDefault();zoom(Math.exp(-event.deltaY*.001));},{passive:false});
    canvas.addEventListener('keydown',event=>{
      const key=event.key;
      if(key==='Escape') {if(brush){brush=null;notifyArea();}else if(areaMode)setAreaSelection(false);clearPreview();schedule();return;}
      if(areaMode && (key.startsWith('Arrow') || key==='Enter')) {
        event.preventDefault();
        if(!brush){const w=canvas.clientWidth,h=canvas.clientHeight;brush=[[w*.35,h*.35],[w*.65,h*.65]];}
        if(key==='Enter'){applyBrush();return;}
        const dx=key==='ArrowLeft'?-10:key==='ArrowRight'?10:0,dy=key==='ArrowUp'?-10:key==='ArrowDown'?10:0;
        if(event.shiftKey){brush[1]=[Math.max(brush[0][0]+8,Math.min(canvas.clientWidth,brush[1][0]+dx)),Math.max(brush[0][1]+8,Math.min(canvas.clientHeight,brush[1][1]+dy))];}
        else {const x=Math.max(-brush[0][0],Math.min(canvas.clientWidth-brush[1][0],dx)),y=Math.max(-brush[0][1],Math.min(canvas.clientHeight-brush[1][1],dy));brush=brush.map(point=>[point[0]+x,point[1]+y]);}
        notifyArea();schedule();return;
      }
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Home','[',']','Enter'].includes(key)) return;
      event.preventDefault();
      if(key.startsWith('Arrow')) {clearPreview();dropAreaBox();}
      if(key==='ArrowLeft') yaw-=.12;if(key==='ArrowRight') yaw+=.12;
      if(key==='ArrowUp') pitch-=.12;if(key==='ArrowDown') pitch+=.12;
      if(key==='+' || key==='=') zoom(1.2);if(key==='-') zoom(1/1.2);
      if(key==='Home') reset();if(key==='[') step(-1);if(key===']') step(1);if(key==='Enter') open();schedule();
    });
    if(typeof ResizeObserver!=='undefined') new ResizeObserver(()=>{clearPreview();dropAreaBox();schedule();}).observe(canvas);
    return {setRuns(next,id) {clearPreview();const robot=next.find(validPosition)?.robot_id;if(robot!==undefined && areaRobot!==undefined && robot!==areaRobot){areaKeys.clear();areaApplied=false;}if(robot!==undefined)areaRobot=robot;rows=next;regionData=null;areaBounds=brush=null;const keys=new Set(rows.filter(validPosition).map(runKey));areaKeys=new Set([...areaKeys].filter(key=>keys.has(key)));refreshArea();selected=rows.some(run=>run.episode_id===id) ? id : '';focused=Math.max(0,rows.findIndex(run=>run.episode_id===selected));focus(rows[focused]);schedule();},
      setHighlight(mode) {highlight=['both','success','failure'].includes(mode)?mode:'none';focus(rows[focused]);schedule();},highlightSummary,
      select(id) {selected=id;schedule();},setAreaSelection,clearArea,clearPreview,reset,zoom,step,open};
  }
  window.yamTaskCloud={create,createPreview,project,offset,outcome,regionsFor,summarizeArea,medianPrompt};
})();
