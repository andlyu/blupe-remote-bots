/* Wait for a verified replay, then promote a final edit after playback. */
(() => {
  'use strict';
  function install() {
    const player=document.getElementById('pastRunVideo'), dialog=document.getElementById('pastRunDialog');
    const history=window.yamReplayHistory, review=window.yamReplayReview;
    if(!player || !dialog || !history) return;
    const panel=document.createElement('div'), bar=document.createElement('progress'), text=document.createElement('p');
    panel.className='replayProcessing'; panel.id='replayProgress'; panel.hidden=true;
    panel.setAttribute('role','status'); panel.setAttribute('aria-live','polite');
    bar.max=100; bar.setAttribute('aria-label','Waiting for replay preparation');
    panel.append(bar,text); player.parentElement.after(panel);
    const baseOpen=history.openRun.bind(history);
    let target=null, timer=null, generation=0, activeSession=null;
    const completed=new Set();
    const valid=id=>typeof id==='string' && /^ep_[A-Za-z0-9_-]{1,100}$/.test(id);
    const terminal=new Set(['stopped','completed','failed','error','timed_out','cancelled','ended','safety_aborted','disconnected']);
    function stop() { generation++;target=null;clearTimeout(timer);panel.hidden=true; }
    function progress(request) {
      panel.hidden=false;bar.removeAttribute('value');
      text.textContent=request.next?'Improved replay ready — it will open after playback ends.':
        request.error?'Replay status unavailable · Retrying…':
        request.quick?'Quick preview ready · Waiting for improved replay.':
        'Waiting for saved replay · Preparation may take a few minutes.';
    }
    function apply(run) {
      const quality=run.video_quality;
      baseOpen(run);
      if(!run.video_url && run.video_status==='processing') begin(run.episode_id,run.robot_id);
      else if(quality==='quick') begin(run.episode_id,run.robot_id,true,run.video_sha256);
      else stop();
    }
    async function poll(request) {
      if(target!==request || !dialog.open) return;
      progress(request);
      try {
        // Some stations publish through the catalog instead of the quick cache.
        // Bound that more expensive fallback to once every five seconds.
        const catalog=Date.now()-request.catalogAt>=5000;
        if(catalog) request.catalogAt=Date.now();
        const response=await fetch(`/api/past-runs?episode_id=${encodeURIComponent(request.id)}&robot_id=${encodeURIComponent(request.robot)}${catalog?'':'&preview=1'}`,
          {cache:'no-store',headers:{'X-Blupe-Robot':request.robot}});
        if(!response.ok) throw new Error('Replay check unavailable');
        const data=await response.json();
        if(target!==request || request.generation!==generation || !dialog.open) return;
        const run=data.runs?.find(row=>row.episode_id===request.id && row.robot_id===request.robot);
        request.error=false;
        if(run?.video_url && run.video_duration_s!==0) {
          if(!request.quick) { apply(run);return; }
          if(run.video_quality!=='quick') {
            if(run.video_sha256===request.sha) {stop();return;}
            if(player.ended || (player.paused && !player.currentTime)) {apply(run);return;}
            request.next=run;progress(request);return;
          }
        }
      } catch(_) {
        if(target!==request || request.generation!==generation || !dialog.open) return;
        request.error=true;progress(request);
      }
      if(target===request && dialog.open) timer=setTimeout(()=>poll(request),Date.now()-request.started<10000?500:2000);
    }
    function begin(id,robot,quick=false,sha=null) {
      if(!valid(id) || !robot) return;
      if(target?.id===id && target.quick===quick && target.sha===sha) return;
      stop();target={id,robot,quick,sha,started:Date.now(),catalogAt:Date.now(),generation};
      if(!quick) {
        const old=document.getElementById('replayProcessing');if(old) old.hidden=true;
      }
      poll(target);
    }
    history.openRun=(run,live=false)=>{
      if(live){stop();return baseOpen(run,live);}
      apply(run);
    };
    if(review) {
      const observe=review.observe.bind(review);
      review.observe=(state,robot,csrf)=>{
        observe(state,robot,csrf);
        if(state.session_id && ['queued','preparing','running'].includes(state.status)) activeSession=state.session_id;
        if(state.session_id===activeSession && terminal.has(state.status) && valid(state.episode_id)
            && !completed.has(state.session_id) && dialog.open) {
          completed.add(state.session_id);begin(state.episode_id,robot);
        }
      };
    }
    player.addEventListener('ended',()=>{if(target?.next && dialog.open) apply(target.next);});
    player.addEventListener('canplay',()=>{
      if(!panel.dataset.firstPlayableAt && panel.dataset.timingStartedAt) {
        panel.dataset.firstPlayableAt=String(Date.now());
        panel.dataset.readyAfterMs=String(Date.now()-Number(panel.dataset.timingStartedAt));
      }
    });
    // Opt-in saved-recording timing view. It only waits for public replay
    // artifacts; this never submits a policy or changes a recording's identity.
    const query=new URLSearchParams(location.search),timingId=query.get('replay_timing');
    if(valid(timingId)) {
      const button=document.createElement('button');button.textContent='Measure saved-run preview delivery';
      button.type='button';button.id='measureReplayDelivery';
      document.getElementById('past-runs')?.prepend(button);
      button.addEventListener('click',()=>{
        const at=Number(query.get('preview_at'))||Date.now();
        button.disabled=true;button.textContent='Timing trial armed';
        setTimeout(()=>{
          review?.ready();player.pause();player.removeAttribute('src');player.load();
          player.parentElement.hidden=true;
          if(!dialog.open) dialog.showModal();
          panel.dataset.timingStartedAt=String(at);
          begin(timingId,document.getElementById('robotSelector')?.value);
        },Math.max(0,at-Date.now()));
      });
    }
    dialog.addEventListener('close',stop);
    window.addEventListener('blupe-robot-selected',()=>{stop();activeSession=null;});
    // Internal history cards call the original lexical openRun. Recognize the
    // immutable local source too, without changing an actively playing clip.
    player.addEventListener('loadstart',()=>{
      const match=/\/api\/quick-replays\/(ep_[A-Za-z0-9_-]+)\/([0-9a-f]{64})\.mp4/.exec(player.src||'');
      if(match && !target && dialog.open) {
        const robot=document.getElementById('robotSelector')?.value;
        begin(match[1],robot,true,match[2]);
      }
    });
  }
  if(document.readyState!=='complete') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
