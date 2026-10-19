/* Quick replay delivery, estimated progress, then a non-disruptive final upgrade. */
(() => {
  'use strict';
  function install() {
    const player=document.getElementById('pastRunVideo'), dialog=document.getElementById('pastRunDialog');
    const history=window.yamReplayHistory, review=window.yamReplayReview;
    if(!player || !dialog || !history) return;
    const panel=document.createElement('div'), bar=document.createElement('progress'), text=document.createElement('p');
    panel.className='replayProcessing'; panel.id='replayProgress'; panel.hidden=true;
    panel.setAttribute('role','status'); panel.setAttribute('aria-live','polite');
    bar.max=100; bar.setAttribute('aria-label','Estimated replay preparation progress');
    panel.append(bar,text); player.parentElement.after(panel);
    const baseOpen=history.openRun.bind(history);
    let target=null, timer=null, generation=0, activeSession=null;
    const completed=new Set();
    const valid=id=>typeof id==='string' && /^ep_[A-Za-z0-9_-]{1,100}$/.test(id);
    const terminal=new Set(['stopped','completed','failed','error','timed_out','cancelled','ended','safety_aborted','disconnected']);
    function stop() { generation++;target=null;clearTimeout(timer);panel.hidden=true; }
    function progress(request) {
      const estimate=request.quick?60000:5000;
      const elapsed=Date.now()-request.started;
      const left=Math.ceil((estimate-elapsed)/1000);
      panel.hidden=false;bar.value=Math.min(95,elapsed/estimate*100);
      text.textContent=request.next?'Improved replay ready — it will open after playback ends.':
        `${request.quick?'Quick preview ready · Improving replay':'Preparing quick preview'}${left>0?` · about ${left} seconds left`:' · Finishing…'}`;
    }
    function apply(run) {
      const quality=run.video_quality;
      baseOpen(run);
      if(quality==='quick') begin(run.episode_id,run.robot_id,true,run.video_sha256);
      else stop();
    }
    async function poll(request) {
      if(target!==request || !dialog.open) return;
      progress(request);
      try {
        const response=await fetch(`/api/past-runs?episode_id=${encodeURIComponent(request.id)}&robot_id=${encodeURIComponent(request.robot)}&preview=1`,
          {cache:'no-store',headers:{'X-Blupe-Robot':request.robot}});
        if(!response.ok) throw new Error('Replay check unavailable');
        const data=await response.json();
        if(target!==request || request.generation!==generation || !dialog.open) return;
        const run=data.runs?.find(row=>row.episode_id===request.id && row.robot_id===request.robot);
        if(run?.video_url && run.video_duration_s!==0) {
          if(!request.quick) { apply(run);return; }
          if(run.video_quality!=='quick' && run.video_sha256!==request.sha) {
            if(player.ended || (player.paused && !player.currentTime)) {apply(run);return;}
            request.next=run;progress(request);return;
          }
        }
      } catch(_) { /* Keep the playable quick clip and retry; never invent readiness. */ }
      if(target===request && dialog.open) timer=setTimeout(()=>poll(request),250);
    }
    function begin(id,robot,quick=false,sha=null) {
      if(!valid(id) || !robot) return;
      if(target?.id===id && target.quick===quick && target.sha===sha) return;
      stop();target={id,robot,quick,sha,started:Date.now(),generation};
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
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
