/* Public spectator video only. This module never creates a robot session. */
export function observerView(C) {
  const $=id=>document.getElementById(id),canvas=$('observerCanvas'),ctx=canvas.getContext('2d'),video=$('observerVideo');
  let selected=null,hls=null,generation=0,timer=null,frame=0,lastTime=-1,lastFrameAt=0,lastPaint=0;
  function stop() {
    generation++;selected=null;clearTimeout(timer);timer=null;cancelAnimationFrame(frame);
    hls?.destroy();hls=null;video.pause();video.removeAttribute('src');video.load();
    canvas.hidden=true;$('observerStatus').textContent='Connecting…';
  }
  function show(station) {
    if(selected===station)return;stop();selected=station;const current=generation;
    lastTime=-1;lastFrameAt=0;lastPaint=0;canvas.dataset.frame='0';delete canvas.dataset.sourceRect;
    const label=$('observerStatus');
    if(station==='yam-1') {
      const load=()=>{
        if(current!==generation)return;
        const image=new Image();
        image.onload=()=>{if(current!==generation)return;canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;ctx.drawImage(image,0,0);canvas.hidden=false;canvas.dataset.frame=String(Number(canvas.dataset.frame)+1);label.textContent='Live · observer';timer=setTimeout(load,800);};
        image.onerror=()=>{if(current!==generation)return;canvas.hidden=true;label.textContent='Observer unavailable · retrying';timer=setTimeout(load,3000);};
        image.src='./api/path-studio/cameras/observer.jpg?station=yam-1&t='+Date.now();
      };load();return;
    }
    const url='./api/path-studio/video/robo-house/index.m3u8';
    video.muted=true;video.playsInline=true;
    function connect() {
      if(current!==generation)return;hls?.destroy();hls=null;label.textContent='Connecting observer…';
      if(window.Hls?.isSupported()) {
        hls=new Hls({enableWorker:false,lowLatencyMode:false,backBufferLength:0,maxBufferLength:4,liveSyncDuration:1,liveMaxLatencyDuration:3,maxLiveSyncPlaybackRate:1.05});
        hls.on(Hls.Events.ERROR,(_,data)=>{if(data.fatal&&current===generation){canvas.hidden=true;label.textContent='Observer unavailable · retrying';clearTimeout(timer);timer=setTimeout(()=>{timer=null;connect();},4000);}});
        hls.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>{label.textContent='Press Play observer';}));
        hls.loadSource(url);hls.attachMedia(video);
      } else if(video.canPlayType('application/vnd.apple.mpegurl')) {video.src=url;video.play().catch(()=>{label.textContent='Press Play observer';});}
      else label.textContent='Observer video unsupported in this browser';
    }
    function paint(now) {
      if(current!==generation)return;
      if(video.readyState>=2&&video.currentTime!==lastTime&&now-lastPaint>=125) {
        const rect=C.observerRect(video.videoWidth,video.videoHeight,station);
        if(canvas.width!==rect[2]||canvas.height!==rect[3]){canvas.width=rect[2];canvas.height=rect[3];}
        ctx.drawImage(video,...rect,0,0,canvas.width,canvas.height);canvas.hidden=false;
        canvas.dataset.frame=String(Number(canvas.dataset.frame||0)+1);canvas.dataset.sourceRect=rect.join(',');
        lastTime=video.currentTime;lastFrameAt=now;lastPaint=now-((now-lastPaint)%125);label.textContent='Live · observer';
      } else if(lastFrameAt&&now-lastFrameAt>5000) {label.textContent='Observer stalled · reconnecting';canvas.hidden=true;if(!timer)timer=setTimeout(()=>{timer=null;connect();},1000);}
      frame=requestAnimationFrame(paint);
    }
    connect();frame=requestAnimationFrame(paint);
  }
  const dialog=$('observerDialog'),home=$('observerPicture');
  $('expandObserver').onclick=()=>{$('observerEmpty').textContent='Observer is expanded.';$('expandedObserver').append(canvas);dialog.showModal();};
  $('closeObserver').onclick=()=>dialog.close();dialog.onclose=()=>{home.prepend(canvas);$('observerEmpty').textContent='Connecting to the observer camera…';};
  $('playObserver').onclick=()=>video.play().catch(()=>{$('observerStatus').textContent='Observer could not play';});
  window.addEventListener('pagehide',stop);
  return {show,stop};
}
