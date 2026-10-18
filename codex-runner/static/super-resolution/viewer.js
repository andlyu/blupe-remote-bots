/* Optional GPU super-resolution for the expanded spectator camera. */
(() => {
  'use strict';
  let current = null, disposed = false;
  const root = '/static/super-resolution/';
  const MAX_AGE_MS = 200, FRAME_BUDGET_MS = 125;
  let enabled = true;
  try { enabled = localStorage.getItem('yam.camera.enhance') !== 'off'; } catch {}

  function close() {
    if (!current) return;
    const state = current; current = null;
    cancelAnimationFrame(state.raf);
    clearTimeout(state.timeout);
    state.worker?.terminate();
    state.overlay.remove(); state.controls.remove();
  }

  function open(source) {
    const picture = source.closest('.syncTilePicture') || source.parentElement;
    const state = current = {source, picture, worker:null, busy:false, ready:false,
      frame:null, lastResult:0, slow:0, sequence:0, raf:0, timeout:0, generation:0};
    const overlay = state.overlay = document.createElement('canvas');
    overlay.className = 'cameraEnhancedImage'; overlay.hidden = true;
    overlay.setAttribute('aria-hidden','true');
    const controls = state.controls = document.createElement('div');
    controls.className = 'cameraEnhancementControls';
    const button = state.button = document.createElement('button');
    button.type = 'button'; button.textContent = 'Enhance';
    button.title = 'GPU super-resolution for this view. Toggle to compare with the original.';
    const status = state.status = document.createElement('span');
    status.setAttribute('role','status');
    controls.append(button,status); picture.append(overlay,controls);
    controls.addEventListener('click',event => event.stopPropagation());
    controls.addEventListener('keydown',event => event.stopPropagation());

    function original(message) {
      overlay.hidden = true; delete source.dataset.enhancementMs;
      status.textContent = message;
    }
    function stopWorker(message) {
      state.generation++;
      clearTimeout(state.timeout); state.worker?.terminate(); state.worker = null;
      state.ready = state.busy = false; original(message);
    }
    function fail(message) {
      if (current !== state) return;
      stopWorker(message); button.setAttribute('aria-pressed','false');
      state.failed = true;
    }
    function startWorker() {
      state.failed = false; button.setAttribute('aria-pressed',String(enabled));
      if (!enabled) { stopWorker('Original'); return; }
      if (!navigator.gpu || !window.Worker || !window.OffscreenCanvas || !window.createImageBitmap) {
        original('Original · enhancement unavailable'); button.setAttribute('aria-pressed','false'); button.disabled = true; return;
      }
      try {
        status.textContent = 'Loading enhancement…';
        const worker = state.worker = new Worker(root+'worker.js');
        worker.onerror = () => fail('Original · enhancement unavailable');
        worker.onmessage = event => {
          const data = event.data;
          if (current !== state || state.worker !== worker || !enabled) { data.bitmap?.close(); return; }
          if (data.type === 'ready') {
            clearTimeout(state.timeout); state.ready = true; status.textContent = 'Enhancement ready'; return;
          }
          clearTimeout(state.timeout); state.busy = false;
          if (data.type === 'error') { fail('Original · enhancement unavailable'); return; }
          if (data.type !== 'frame') return;
          const age = performance.now()-data.started;
          if (document.hidden || !source.isConnected || age > MAX_AGE_MS || data.elapsed > FRAME_BUDGET_MS) {
            data.bitmap?.close();
            if (++state.slow >= 3) fail('Original · enhancement too slow on this device');
            return;
          }
          state.slow = 0;
          overlay.width = data.width; overlay.height = data.height;
          overlay.getContext('2d',{alpha:false}).drawImage(data.bitmap,0,0);
          data.bitmap.close(); overlay.hidden = false;
          state.lastResult = performance.now(); status.textContent = 'Enhanced · +' + Math.round(age) + ' ms';
          source.dataset.enhancementMs = data.elapsed.toFixed(1);
          source.dataset.enhancedFrame = String(data.sequence);
        };
        state.timeout = setTimeout(()=>fail('Original · enhancement unavailable'),20000);
        worker.postMessage({type:'init'});
      } catch { fail('Original · enhancement unavailable'); }
    }
    button.addEventListener('click',()=>{
      enabled = state.failed ? true : !enabled;
      try {localStorage.setItem('yam.camera.enhance',enabled?'on':'off');} catch {}
      stopWorker(enabled?'Loading enhancement…':'Original'); startWorker();
    });
    function paint() {
      if (current !== state) return;
      if (document.hidden || performance.now()-state.lastResult > MAX_AGE_MS) overlay.hidden = true;
      const frame = source.dataset.presentedFrame;
      if (enabled && state.ready && !state.busy && !state.failed && !document.hidden &&
          source.dataset.frameSource === 'video' && frame && frame !== state.frame && source.width && source.height) {
        state.busy = true; state.frame = frame;
        const started = performance.now(), sequence = ++state.sequence;
        const worker = state.worker, generation = state.generation;
        // createImageBitmap snapshots one immutable canvas frame. Keep one job
        // in flight; skipped input frames are never queued.
        createImageBitmap(source).then(bitmap=>{
          if (current !== state || !enabled || state.worker !== worker || generation !== state.generation) {bitmap.close();return;}
          state.timeout = setTimeout(()=>fail('Original · enhancement too slow on this device'),2000);
          state.worker.postMessage({type:'frame',bitmap,started,sequence},[bitmap]);
        }).catch(()=>fail('Original · enhancement unavailable'));
      }
      state.raf = requestAnimationFrame(paint);
    }
    startWorker(); paint();
  }

  function synchronize() {
    if (disposed) return;
    if (document.hidden) {close();return;}
    const container = document.fullscreenElement || document.querySelector('.cameraDialog[open]');
    const source = container?.querySelector('canvas[data-sync-tile]');
    if (source === current?.source) return;
    close(); if (source) open(source);
  }
  const observer = new MutationObserver(synchronize);
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','open']});
  document.addEventListener('fullscreenchange',synchronize);
  document.addEventListener('visibilitychange',()=>{
    // Terminate rather than let a hidden tab retain a GPU job or old result.
    if(document.hidden) close(); else synchronize();
  });
  window.addEventListener('pagehide',()=>{disposed=true;observer.disconnect();close();});
  synchronize();
})();
