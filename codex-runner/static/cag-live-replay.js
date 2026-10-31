/* Retain the actual displayed observer camera while the policy runs.
 * No microphone, device capture, synthetic robot frames or uploads. The native
 * source recording remains independent and replaces this viewing copy later. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const finished = new Set(['stopped','completed','failed','error','timed_out','cancelled','ended','safety_aborted','disconnected']);
  const clips = new Map();
  let active = null, objectURL = null, database;
  const panel = document.createElement('section');
  panel.id = 'cagLiveReplays'; panel.hidden = true;
  const heading = document.createElement('h3'); heading.textContent = 'Live-view recordings saved in this browser';
  const note = document.createElement('p'); note.className = 'help';
  note.textContent = 'Actual camera footage at normal speed. These local copies are available immediately; archived robot recordings also appear in Your runs.';
  const list = document.createElement('ul');
  panel.append(heading, note, list);
  $('myRunsList').parentElement.append(panel);
  const dialog = document.createElement('dialog'); dialog.id = 'cagLiveReplayDialog';
  dialog.setAttribute('aria-labelledby','cagLiveReplayTitle');
  const title = document.createElement('h2'); title.id = 'cagLiveReplayTitle';
  const details = document.createElement('p'), player = document.createElement('video');
  player.controls = true; player.playsInline = true; player.preload = 'metadata';
  player.style.cssText = 'width:100%;max-height:65vh;background:#111';
  const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close live-view replay';
  const download = document.createElement('a'); download.textContent = 'Save video';
  dialog.append(title, details, player, download, close); document.body.append(dialog);
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    player.pause(); player.removeAttribute('src'); player.load();
    if (objectURL) URL.revokeObjectURL(objectURL); objectURL = null;
  });
  function db() {
    if (!database) database = new Promise((resolve, reject) => {
      const open = indexedDB.open('blupe-cag-live-replays', 1);
      open.onupgradeneeded = () => open.result.createObjectStore('clips', {keyPath:'episode_id'});
      open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
    });
    return database;
  }
  async function persist(clip) {
    const store = (await db()).transaction('clips','readwrite');
    store.objectStore('clips').put(clip);
    await new Promise((resolve,reject) => {store.oncomplete=resolve;store.onerror=()=>reject(store.error);store.onabort=()=>reject(store.error);});
  }
  function render() {
    list.replaceChildren(); panel.hidden = clips.size === 0;
    for (const clip of [...clips.values()].sort((a,b)=>b.started_at-a.started_at)) {
      const row = document.createElement('li'), button = document.createElement('button');
      button.type='button'; button.textContent=`▶ ${clip.runner_name} · ${clip.approach} · ${new Date(clip.started_at).toLocaleTimeString()} · ${clip.prompt}`;
      button.addEventListener('click',()=>open(clip.episode_id)); row.append(button);list.append(row);
    }
  }
  function open(id) {
    const clip=clips.get(id); if(!clip) return false;
    window.yamReplayReview?.ready();
    if ($('pastRunDialog')?.open) $('pastRunDialog').close();
    if(objectURL) URL.revokeObjectURL(objectURL);
    objectURL=URL.createObjectURL(clip.blob);
    title.textContent=`${clip.runner_name} · ${clip.approach}`;
    details.textContent=`${clip.prompt} · Actual live camera recording${clip.partial?' (first part only)':''} · 1×, pauses retained · Saved in this browser${clip.storage_error?' (browser storage unavailable; use Save video)':''}. This viewing copy includes the live stream’s delay; the source recording is retained separately.`;
    player.src=objectURL;player.defaultPlaybackRate=player.playbackRate=1;
    download.href=objectURL;download.download=clip.episode_id+(clip.blob.type.includes('mp4')?'.mp4':'.webm');
    if(!dialog.open) dialog.showModal();player.play().catch(()=>{});
    return true;
  }
  function status(text) {
    const target=$('cagReplayStatus'); if(target) target.textContent=text;
  }
  function stop(reason = 'run_finished') {
    const run=active;if(!run || run.stopping) return;
    run.stopping=true;run.finished_at=Date.now();run.partial=reason!=='run_finished';clearInterval(run.paint);
    status(run.partial?'Saving the first part of the live view; the source recording continues.':'Run finished · saving the live-view recording…');
    run.recorder.stop();
  }
  function start(state) {
    if(!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) {
      status('This browser cannot save an immediate viewing copy. The robot’s recorded replay will appear in Your runs.');return;
    }
    const source=document.querySelector('#liveViewer canvas[data-camera-role="observer"]');
    // A startup still or a disconnected camera must never become a claimed replay.
    if(!source || source.dataset.frameSource!=='video' || !source.width || !source.height) return;
    const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mime) return;
    const canvas=document.createElement('canvas');canvas.width=640;canvas.height=384;
    const context=canvas.getContext('2d',{alpha:false});
    let last=null, changed=0, changedAt=0;
    const run={episode_id:state.episode_id,session_id:state.session_id,runner_name:state.runner_name || $('runnerName').value,
      approach:state.provider?.approach || state.run_configuration?.approach || window.yamApplication.modelDisplayName(),
      prompt:state.task || $('prompt').value,started_at:Date.now(),chunks:[],bytes:0,stopping:false};
    const paint=()=>{
      if(active!==run) return;
      const frame=source.dataset.presentedFrame;
      if(source.dataset.frameSource==='video' && frame!==last) {last=frame;changed++;changedAt=Date.now();}
      const live=source.isConnected && source.dataset.frameSource==='video' && Date.now()-changedAt<2000;
      context.fillStyle='#111';context.fillRect(0,0,640,384);
      context.drawImage(source,0,24,640,360);
      context.fillStyle='#fff';context.font='13px sans-serif';
      context.fillText(`${live?'ACTUAL LIVE VIEW':'LIVE VIEW PAUSED'} · ${new Date().toISOString()}`,8,17);
    };
    try {
      active=run;paint();
      const stream=canvas.captureStream(8);
      run.recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:800000});
      run.recorder.addEventListener('dataavailable',event=>{
        if(event.data.size) {run.chunks.push(event.data);run.bytes+=event.data.size;}
        // Bound local capture memory; source recording continues independently.
        if(run.bytes>48*1024*1024 && !run.stopping) stop('memory_limit');
      });
      run.recorder.addEventListener('error',()=>{run.capture_error=true;status('Live-view capture failed. Use the archived robot replay in Your runs.');if(!run.stopping) stop();});
      run.recorder.addEventListener('stop',async()=>{
        stream.getTracks().forEach(track=>track.stop());if(active===run) active=null;
        if(changed<3 || run.capture_error || !run.chunks.length) {status('No usable live-view recording. The source replay will appear in Your runs.');return;}
        const clip={episode_id:run.episode_id,runner_name:run.runner_name,approach:run.approach,prompt:run.prompt,
          started_at:run.started_at,finished_at:run.finished_at,partial:run.partial,unique_camera_frames:changed,
          blob:new Blob(run.chunks,{type:mime})};
        clips.set(clip.episode_id,clip);render();
        status('Live-view replay ready · saved in this browser. Archived source replay is also being prepared.');
        $('cagReplayStatus').dataset.readyAt=String(Date.now());if(!run.partial) open(clip.episode_id);
        try {await persist(clip);} catch(_) {clip.storage_error=true;status('Live-view replay ready for this page. Browser storage is unavailable; use Save video to retain it.');}
      });
      run.recorder.start(1000);run.paint=setInterval(paint,125);
      status('Saving the live camera view for immediate replay. The robot’s source recording is retained separately.');
    } catch(_) {active=null;status('Immediate live-view capture is unavailable. Use the archived robot replay in Your runs.');}
  }
  window.cagLiveReplay={observe(state){
    if(active && state.session_id===active.session_id && finished.has(state.status)) stop();
    else if(!active && state.status==='running' && /^ep_[A-Za-z0-9_-]+$/.test(state.episode_id || '') && !clips.has(state.episode_id)) start(state);
  },open};
  const statusNode=document.createElement('p');statusNode.id='cagReplayStatus';statusNode.className='help';statusNode.setAttribute('role','status');
  const place=()=>{if($('cagStatus')) $('cagStatus').after(statusNode);};
  document.addEventListener('DOMContentLoaded',place,{once:true});
  const existing=window.yamApplication.sessionReady;
  window.yamApplication.sessionReady=function(...args){const value=existing.apply(this,args);place();return value;};
  db().then(database=>new Promise((resolve,reject)=>{
    const query=database.transaction('clips').objectStore('clips').getAll();query.onsuccess=()=>resolve(query.result);query.onerror=()=>reject(query.error);
  })).then(rows=>{for(const row of rows) if(row.blob instanceof Blob) clips.set(row.episode_id,row);render();}).catch(()=>{});
})();
