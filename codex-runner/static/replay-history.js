/* Nonmodal replay inspector and bounded, lazy related-video browsing. */
(() => {
  'use strict';
  const validXYZ = row => Array.isArray(row.xyz) && row.xyz.length === 3 && row.xyz.every(Number.isFinite);
  const normalized = text => String(text || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
  const words = text => new Set(normalized(text).split(' ').filter(word => word && !['the','a','an','to','of','on','in','it','please','robot','up','down','with','for','and','then','at','from','me','you','can','do'].includes(word)));
  function rankSimilar(selected, rows, limit = 40) {
    const sameRobot=rows.filter(row=>row.robot_id===selected.robot_id);
    const reference={...sameRobot.find(row=>row.episode_id===selected.episode_id),...selected};
    const task=normalized(reference.prompt), tokens=words(reference.prompt), seen=new Set();
    return sameRobot.filter(row=>{
      if (!row.episode_id || row.episode_id===reference.episode_id || seen.has(row.episode_id)) return false;
      if ((row.preview?.video_duration_s ?? row.video_duration_s) === 0 || row.video_status === 'unavailable') return false;
      const published=!!row.preview?.video_url || !!row.video_url || row.original_available === true;
      if(published)seen.add(row.episode_id);
      return published;
    }).map(row=>{
      const exact=!!task && normalized(row.prompt)===task;
      const distance=validXYZ(reference) && validXYZ(row) ? Math.sqrt(reference.xyz.reduce((sum,value,i)=>sum+(value-row.xyz[i])**2,0)) : null;
      const other=words(row.prompt), common=[...tokens].filter(word=>other.has(word)).length;
      const overlap=common/Math.max(1,new Set([...tokens,...other]).size);
      return {row,exact,distance,overlap};
    }).filter(item=>item.exact || (item.distance!==null ? item.overlap>=.4 || (item.overlap>=.2 && item.distance<=.2) : item.overlap>=.25))
      .sort((a,b)=>Number(b.exact)-Number(a.exact) || b.overlap-a.overlap || (a.distance ?? 1)-(b.distance ?? 1) || (b.row.started_at || 0)-(a.row.started_at || 0) || a.row.episode_id.localeCompare(b.row.episode_id))
      .slice(0,limit).map(item=>item.row);
  }
  function similarSuccessSummary(rows, source) {
    const nearest=rows.slice(0,10), counts={Success:0,Failure:0,Uncertain:0,Unscored:0};
    if(!nearest.length)return 'No similar published runs to score.';
    for(const row of nearest){const label=window.yamRunLabels?.outcome(row,source) || 'Unscored';counts[label in counts?label:'Unscored']++;}
    const scored=counts.Success+counts.Failure;
    const basis=nearest.length===10?'the 10 closest similar runs':`${nearest.length} available similar ${nearest.length===1?'run':'runs'}`;
    const result=scored ? `${(counts.Success/scored*100).toFixed(1)}% success (${counts.Success}/${scored} Success/Failure labels) across ${basis}.` : `No Success/Failure labels among ${basis}.`;
    return `${result} ${counts.Uncertain} Uncertain and ${counts.Unscored} unlabeled or excluded. ${source==='auto'?'Auto-labeled':'Human-labeled'}.`;
  }
  window.yamSimilarRuns={rank:rankSimilar,summary:similarSuccessSummary};
  const $=id=>document.getElementById(id), dialog=$('pastRunDialog'), body=$('runSidebarBody'), list=$('similarRunsList');
  if (!dialog?.classList?.contains('runSidebar') || !body || !list) return;
  const status=$('similarRunsStatus'), score=$('similarRunsScore'), more=$('moreSimilarRuns'), sentinel=$('similarRunsSentinel'), catalog=new Map();
  let active=null, source=$('pastRunsLabelSource')?.value==='human'?'human':'auto', scope=null, signature='', returnFocus=null, catalogRevision=0, filters={models:[],query:''};
  const catalogKey = robot => JSON.stringify([robot,filters.models,filters.query]);
  function rememberCatalog(key,rows) {
    catalog.delete(key);catalog.set(key,{rows,at:Date.now(),version:++catalogRevision});
    while(catalog.size>6)catalog.delete(catalog.keys().next().value);
  }
  const stateText=row=>{
    const label=window.yamRunLabels?.outcome(row,source) || 'Unscored';
    return `${source==='auto'?'Auto':'Human'}: ${label==='Unscored'?'Unlabeled or excluded':label}`;
  };
  function cancelScope() {
    if (!scope) return;
    scope.closed=true;scope.controllers.forEach(controller=>controller.abort());
    scope.mediaObserver?.disconnect();scope.moreObserver?.disconnect();
    for (const entry of scope.media.values()) {entry.video.pause();entry.video.removeAttribute('src');entry.video.load();}
    scope=null;
  }
  function updateCount(request) {
    if (scope!==request || request.closed) return;
    status.textContent=request.rows.length
      ? `Showing ${request.shown} of ${request.rows.length} similar published videos on this robot. ${source==='auto'?'Auto-labeled':'Human-labeled'} results. ${request.shown<request.rows.length?'Scroll for more.':'All suggestions shown.'}`
      : 'No similar published videos found on this robot yet.';
    more.hidden=request.shown>=request.rows.length;
  }
  function release(request,entry) {
    entry.controller?.abort();entry.video.pause();entry.video.removeAttribute('src');entry.video.load();request.media.delete(entry.id);
  }
  function pump(request) {
    if (request.closed) return;
    while(request.busy<2 && request.queue.length) {
      const entry=request.queue.shift();entry.queued=false;
      if (!entry.visible || entry.video.hasAttribute('src')) continue;
      const controller=new AbortController();entry.controller=controller;request.controllers.add(controller);request.busy++;
      (async()=>{
        try {
          let detail=entry.run.preview?.video_url ? entry.run.preview : entry.run.video_url ? entry.run : null;
          if (!detail) {
            const response=await fetch(`/api/past-runs?episode_id=${encodeURIComponent(entry.run.episode_id)}&robot_id=${encodeURIComponent(request.robot)}`,{cache:'no-store',signal:controller.signal,headers:{'X-Blupe-Robot':request.robot}});
            if (!response.ok) throw new Error();
            const data=await response.json();detail=data.runs?.find(row=>row.episode_id===entry.run.episode_id && row.robot_id===request.robot);
          }
          if (request.closed || controller.signal.aborted || !entry.visible) return;
          if (!detail?.video_url || detail.video_duration_s===0 || detail.video_status==='unavailable') {entry.note.textContent='Preview unavailable · select for run details';return;}
          while(request.media.size>=6) {const oldest=[...request.media.values()].find(other=>other!==entry);if (!oldest) break;release(request,oldest);}
          request.media.set(entry.id,entry);entry.video.preload='metadata';entry.video.src=detail.video_url;
          entry.video.defaultPlaybackRate=entry.video.playbackRate=entry.run.replay_speed===2 ? 2/(detail.compressed?(detail.preview_speed || 10):1) : detail.compressed?1:10;
          entry.note.textContent='Loading preview…';
        } catch (_) {if(!controller.signal.aborted && !request.closed)entry.note.textContent='Preview unavailable · select to retry';}
        finally {request.controllers.delete(controller);request.busy--;pump(request);}
      })();
    }
  }
  function enqueue(request,entry) {
    if (request.closed || entry.queued || entry.video.hasAttribute('src')) return;
    entry.queued=true;request.queue.push(entry);pump(request);
  }
  function append(request, count=8) {
    if (request.closed || scope!==request) return;
    for (const row of request.rows.slice(request.shown,request.shown+count)) {
      const li=document.createElement('li'), button=document.createElement('button'), video=document.createElement('video'), text=document.createElement('span'), title=document.createElement('strong'), meta=document.createElement('span'), note=document.createElement('span');
      button.type='button';button.className='similarRunCard';button.setAttribute('aria-label',`Watch similar run: ${row.prompt || 'Task not recorded'}`);
      video.muted=true;video.playsInline=true;video.loop=true;video.preload='none';video.setAttribute('aria-hidden','true');video.tabIndex=-1;
      text.className='similarRunText';title.textContent=row.prompt || 'Task not recorded';meta.className='similarRunMeta';meta.textContent=`${stateText(row)} · ${row.model || 'Model not recorded'}`;note.className='similarRunState';note.textContent=request.mediaObserver?'Preview loads when visible':'Hover or focus to preview';
      text.append(title,meta,note);button.append(video,text);li.append(button);list.append(li);
      const entry={id:row.episode_id,run:row,video,note,visible:false,queued:false};request.entries.set(li,entry);
      button.addEventListener('click',()=>window.yamReplayHistory?.selectRun(row));
      button.addEventListener('pointerenter',()=>{if(!entry.visible && request.mediaObserver)return;entry.visible=true;for(const other of request.media.values())if(other!==entry)other.video.pause();enqueue(request,entry);if(video.hasAttribute('src')&&!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)video.play().catch(()=>{});});
      button.addEventListener('focus',()=>{if(!request.mediaObserver){entry.visible=true;enqueue(request,entry);}});
      const leave=()=>{video.pause();if(!request.mediaObserver){entry.visible=false;release(request,entry);}};
      button.addEventListener('pointerleave',leave);button.addEventListener('blur',leave);
      video.addEventListener('loadedmetadata',()=>{if(video.hasAttribute('src')&&video.duration>0)video.currentTime=Math.min(1,video.duration/2);});
      const previewReady=()=>{if(!request.closed && video.hasAttribute('src'))note.textContent='Select to watch';};
      video.addEventListener('seeked',previewReady);video.addEventListener('loadeddata',previewReady);
      video.addEventListener('error',()=>{if(!request.closed && video.hasAttribute('src'))note.textContent='Preview unavailable · select to retry';});
      if(request.mediaObserver)request.mediaObserver.observe(li);
      else if(request.shown<3){entry.visible=true;enqueue(request,entry);}
      request.shown++;
    }
    updateCount(request);
  }
  async function refresh(force=false) {
    if (!active || !dialog.open) return;
    const key=catalogKey(active.robot_id), cached=catalog.get(key), nextSignature=`${key}:${active.episode_id}:${source}:${cached?.version || 0}`;
    if(!force && signature===nextSignature)return;
    signature=nextSignature;const oldShown=scope?.shown || 8;cancelScope();list.replaceChildren();more.hidden=true;more.textContent='Show more similar videos';status.textContent='Finding similar videos…';if(score)score.textContent='';
    const request=scope={run:{...active},robot:active.robot_id,filters:{models:filters.models.slice(),query:filters.query},closed:false,controllers:new Set(),media:new Map(),entries:new Map(),queue:[],busy:0,shown:0,rows:[]};
    try {
      let rows=cached && Date.now()-cached.at<60000 ? cached.rows : null;
      if (!rows) {
        const controller=new AbortController();request.controllers.add(controller);
        const modelQuery=request.filters.models.map(model=>`&model=${encodeURIComponent(model)}`).join(''), query=request.filters.query?`&q=${encodeURIComponent(request.filters.query)}`:'';
        const response=await fetch(`/api/run-catalog?view=cloud&robot_id=${encodeURIComponent(request.robot)}${modelQuery}${query}`,{cache:'no-store',signal:controller.signal,headers:{'X-Blupe-Robot':request.robot}});
        if(!response.ok)throw new Error();const data=await response.json();rows=data.runs || [];
        if(request.closed)return;rememberCatalog(key,rows);
      }
      await window.yamRunLabels?.load();if(request.closed || scope!==request)return;
      request.rows=rankSimilar(request.run,rows);
      if(score)score.textContent=similarSuccessSummary(request.rows,source);
      if(typeof IntersectionObserver!=='undefined') {
        request.mediaObserver=new IntersectionObserver(entries=>{
          for(const observed of entries){const entry=request.entries.get(observed.target);if(!entry)continue;entry.visible=observed.isIntersecting;if(entry.visible)enqueue(request,entry);else release(request,entry);}
        },{root:body,rootMargin:'80px 0px'});
        request.moreObserver=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)&&request.shown<request.rows.length)append(request);},{root:body,rootMargin:'0px 0px 120px 0px'});
      }
      append(request,Math.max(8,oldShown));request.moreObserver?.observe(sentinel);
    } catch (_) {
      if(request.closed || scope!==request)return;
      status.textContent='Similar videos are unavailable. Retry to load them.';more.textContent='Retry similar videos';more.hidden=false;
    }
  }
  window.yamRunSidebar={
    open(run) {
      const changed=!active || active.episode_id!==run.episode_id || active.robot_id!==run.robot_id;
      const switchingInside=changed && dialog.open && dialog.contains(document.activeElement);
      if(!dialog.open || !dialog.contains(document.activeElement))returnFocus=document.activeElement;
      active={...(changed?{}:active),...run};if(changed){signature='';cancelScope();body.scrollTop=0;}
      document.body.classList.add('runSidebarOpen');if(!dialog.open)dialog.show();
      if(switchingInside)$('closePastRun')?.focus({preventScroll:true});
      refresh();
    },
    setCatalog(rows,{robot,complete,source:labelSource,filters:nextFilters}) {
      source=labelSource || source;
      if(nextFilters)filters={models:[...(nextFilters.models || [])].sort(),query:nextFilters.query || ''};
      if(complete)rememberCatalog(catalogKey(robot),rows.slice());
      if(dialog.open && active?.robot_id===robot)refresh();
    },
    setSource(value) {source=value;signature='';refresh();}
  };
  more.addEventListener('click',()=>{if(scope?.rows.length)append(scope);else refresh(true);});
  dialog.addEventListener('close',()=>{cancelScope();active=null;signature='';document.body.classList.remove('runSidebarOpen');if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});});
  document.addEventListener('keydown',event=>{if(event.key==='Escape' && dialog.open && !document.querySelector?.('dialog:modal') && !document.fullscreenElement && !$('pastRunVideo').webkitDisplayingFullscreen){event.preventDefault();dialog.close();}});
  window.addEventListener('blupe-robot-selected',event=>{if(dialog.open && active?.robot_id!==event.detail)dialog.close();});
})();

/* Personal public-run history and the post-run processing-to-replay transition. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('myRunsList')) return;
  const validId = value => typeof value === 'string' && /^ep_[A-Za-z0-9_-]{1,100}$/.test(value);
  let saved = [];
  let robot = null, token = '', historyToken = '', generation = 0, searchVersion = 0, next = null;
  let pending = null, timer = null, reviewTimer = null, lastMineAt = 0;
  const processingRuns = new Set();
  const activeSessions = new Set(), completedSessions = new Set();
  const dialog = $('pastRunDialog'), player = $('pastRunVideo');
  const processing = $('replayProcessing');
  if (!$('replayRunAnother')) {
    const again = document.createElement('button'); again.id = 'replayRunAnother';
    again.type = 'button'; again.textContent = 'Close and run another';
    const advanced=$('runSidebarDetails')?.querySelector?.('summary');
    if(advanced)advanced.after(again);else $('pastRunDetails').after(again);
    again.addEventListener('click', () => {
      dialog.close();
      const target = new URL(location.href); target.searchParams.delete('run');
      window.history.replaceState(null, '', target);
      $('prompt')?.scrollIntoView({behavior:'smooth', block:'center'}); $('prompt')?.focus();
    });
  }
  const query = new URLSearchParams(location.search);
  let linkedOpened = false;
  const terminal = new Set(['stopped', 'completed', 'failed', 'error', 'timed_out', 'cancelled', 'ended', 'safety_aborted', 'disconnected']);
  function ready() {
    window.yamReplayEmail?.setRun(null);
    pending = null;
    clearTimeout(timer);
    clearTimeout(reviewTimer);
    if ($('assessmentWindow')) $('assessmentWindow').hidden = true;
    processing.hidden = true;
    player.parentElement.hidden = false;
  }
  function remember(state) {
    if (!validId(state.episode_id)) return;
    const row = {episode_id: state.episode_id, robot_id: robot, prompt: state.task || state.prompt || $('prompt')?.value || 'Your latest run', started_at: state.run_started_at || Date.now() / 1000};
    saved = [row, ...saved.filter(item => item.episode_id !== row.episode_id)].slice(0, 100);
  }
  function card(run) {
    const li = document.createElement('li'), button = document.createElement('button');
    button.type = 'button'; button.className = 'pastRunCard personalRunCard';
    const title = document.createElement('span'); title.className = 'pastRunPrompt';
    title.textContent = run.prompt || 'Your run';
    const label = document.createElement('span'); label.className = 'pastRunWatch';
    label.textContent = run.video_url ? '▶ Watch replay' : '◷ Processing replay';
    button.append(title, label);
    button.addEventListener('click', () => openEpisode(run.episode_id, run));
    li.append(button);
    return li;
  }
  async function loadMine(offset = 0) {
    if (!robot || !token) return;
    const version = ++searchVersion, scope = generation; lastMineAt = Date.now();
    $('myRunsStatus').textContent = 'Finding your runs…';
    try {
      const response = await fetch('/api/my-runs', {method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: {'Content-Type': 'application/json', 'X-YAM-Runner-Token': token, 'X-Blupe-Robot': robot},
        body: JSON.stringify({offset})});
      if (!response.ok) throw new Error('Could not load your runs. Select Refresh to retry.');
      const data = await response.json();
      if (scope !== generation || version !== searchVersion) return;
      if (!offset) $('myRunsList').replaceChildren();
      const rows = data.runs || [];
      for (const row of rows) processingRuns.delete(row.episode_id);
      if (!offset) {
        const published = new Set(rows.map(row => row.episode_id));
        for (const row of saved.filter(item => item.robot_id === robot && !published.has(item.episode_id)).slice(0, 3)) {
          // Only the just-finished episode is known to be processing. Older
          // unpublished entries may have failed publication; do not claim progress.
          if (processingRuns.has(row.episode_id)) $('myRunsList').append(card(row));
        }
      }
      for (const row of rows) $('myRunsList').append(card(row));
      next = data.next_offset; $('moreMyRuns').hidden = next == null;
      $('myRunsStatus').textContent = $('myRunsList').children.length
        ? 'Showing runs from your current session.' : 'No runs in this session yet.';
    } catch (error) {
      if (scope === generation && version === searchVersion) $('myRunsStatus').textContent = error.message;
    }
  }
  function renderSummary(run) {
    $('pastRunTitle').textContent = `${run.runner_name || 'Run replay'} · ${run.episode_index == null ? 'Recent run' : 'Run #'+run.episode_index}`;
    $('pastRunPrompt').textContent = run.prompt || '';
    window.yamRunAssessment?.showReplay(run);
    const reason = run.ending_reason || run.result_reason;
    $('pastRunDetails').textContent = [run.model ? `${run.model} · ${run.model_version || 'version unknown'}` : 'Model not recorded · version unknown', [run.result, reason].filter(Boolean).join(': ')].filter(Boolean).join(' · ');
    window.yamRunLabels?.showReplay(run, $('pastRunDetails'));
    renderRunMetrics($('pastRunMetricsSummary'), run.run_metrics, 'stopped');
    renderStepMetricsChart($('pastRunMetricsChart'), run.step_timings);
  }
  function openEpisode(id, known = {}) {
    if (!validId(id) || !robot) return;
    known = {...known,episode_id:id,robot_id:robot};
    ready();
    pending = {id, robot, generation, known};
    if (!window.yamRunSidebar) $('past-runs').scrollIntoView({behavior: 'smooth', block: 'start'});
    player.pause(); player.yamRecordingView?.(); player.yamRecordingView = null;
    player.removeAttribute('src'); player.load(); player.parentElement.hidden = true;
    processing.hidden = false;
    if ($('pastRunSpeed')) $('pastRunSpeed').hidden = true;
    renderSummary(known);
    $('pastRunError').textContent = '';
    if (window.yamRunSidebar) window.yamRunSidebar.open({...known,episode_id:id,robot_id:robot});
    else if (!dialog.open) dialog.showModal();
    poll(pending);
  }
  async function poll(request) {
    try {
      const response = await fetch(`/api/past-runs?episode_id=${encodeURIComponent(request.id)}&robot_id=${encodeURIComponent(request.robot)}`,
        {cache: 'no-store', headers: {'X-Blupe-Robot': request.robot}});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (pending !== request || request.generation !== generation || !dialog.open) return;
      $('pastRunError').textContent = '';
      const run = data.runs?.find(row => row.episode_id === request.id && row.robot_id === request.robot);
      if (run) {
        request.known = {...request.known, ...run, model:run.model || request.known.model, model_version:run.model_version || request.known.model_version};
        renderSummary(request.known);
      }
      if (run && run.video_duration_s !== 0 && run.video_url) {
        processingRuns.delete(run.episode_id);
        window.yamReplayHistory.openRun(request.known);
        loadMine(); window.yamReplayHistory.refresh();
        return;
      }
      if (run?.video_status === 'unavailable') {
        ready(); $('pastRunError').textContent = 'Recorded replay is unavailable. Try again later; run details are still available.'; return;
      }
      if (run?.video_duration_s === 0) {
        processingRuns.delete(request.id);
        ready(); $('pastRunError').textContent = 'This run has no recorded video.';
        return;
      }
    } catch (_) {
      if (pending === request) $('pastRunError').textContent = 'Replay is not available yet. Checking again shortly…';
    }
    if (pending === request && dialog.open) timer = setTimeout(() => poll(request), 5000);
  }
  function observe(state, selectedRobot, csrf) {
    if (historyToken && historyToken !== csrf) {
      ready(); saved = []; processingRuns.clear(); activeSessions.clear(); completedSessions.clear();
      searchVersion++; $('myRunsList').replaceChildren(); delete $('myRunsList').dataset.loaded;
    }
    historyToken = csrf;
    token = csrf;
    if (!robot) robot = selectedRobot;
    if (robot !== selectedRobot) return;
    const sid = state.session_id;
    if (sid && ['queued', 'preparing', 'running'].includes(state.status)) {
      activeSessions.add(sid); remember(state);
    }
    if (sid && activeSessions.has(sid) && terminal.has(state.status) && validId(state.episode_id) && !completedSessions.has(sid)) {
      completedSessions.add(sid); remember(state); processingRuns.add(state.episode_id);
      const known = {...saved[0], runner_name:state.runner_name || $('runnerName')?.value,
        run_metrics:state.run_metrics, step_timings:state.step_timings};
      const scope = generation, id = state.episode_id;
      if ($('assessmentWindow')) $('assessmentWindow').hidden = false;
      // Recording/V0 processing starts at termination on the recorder. Begin
      // checking its public receipt immediately, concurrently with this window.
      fetch(`/api/past-runs?episode_id=${encodeURIComponent(id)}&robot_id=${encodeURIComponent(robot)}&preview=1`,
        {cache:'no-store',headers:{'X-Blupe-Robot':robot}}).then(response => response.ok ? response.json() : null)
        .then(data => { if (scope === generation) Object.assign(known, data?.runs?.find(run => run.episode_id === id) || {}); }).catch(() => {});
      clearTimeout(reviewTimer);
      reviewTimer = setTimeout(() => { if (scope === generation) openEpisode(id, known); }, 5000);
      loadMine();
    }
    if (processingRuns.size && token && Date.now() - lastMineAt > 10000) loadMine();
    if (!$('myRunsList').dataset.loaded && token) { $('myRunsList').dataset.loaded = 'true'; loadMine(); }
  }
  window.yamReplayReview = {observe, openEpisode, ready};
  dialog.addEventListener('close', ready);
  $('moreMyRuns').addEventListener('click', () => { if (next != null) loadMine(next); });
  $('refreshPastRuns').addEventListener('click', () => loadMine());
  window.addEventListener('blupe-robot-selected', event => {
    ready(); robot = event.detail; generation++; token = ''; searchVersion++;
    $('myRunsList').replaceChildren(); delete $('myRunsList').dataset.loaded;
    if (!linkedOpened && validId(query.get('run')) && (!query.get('robot_id') || query.get('robot_id') === robot)) {
      linkedOpened = true; openEpisode(query.get('run'));
    }
  });
})();
