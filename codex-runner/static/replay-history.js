/* Personal public-run history and the post-run processing-to-replay transition. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('myRunsList')) return;
  const storageKey = 'yam-replay-history-v1';
  const validId = value => typeof value === 'string' && /^ep_[A-Za-z0-9_-]{1,100}$/.test(value);
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem(storageKey) || '[]').filter(row => validId(row.episode_id)).slice(0, 100); } catch (_) {}
  let robot = null, token = '', generation = 0, searchVersion = 0, email = '', next = null;
  let pending = null, timer = null, lastMineAt = 0;
  const processingRuns = new Set();
  const activeSessions = new Set(), completedSessions = new Set();
  const dialog = $('pastRunDialog'), player = $('pastRunVideo');
  const processing = $('replayProcessing');
  if (!$('replayRunAnother')) {
    const again = document.createElement('button'); again.id = 'replayRunAnother';
    again.type = 'button'; again.textContent = 'Close and run another';
    $('pastRunDetails').after(again);
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
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify(saved.slice(0, 100))); } catch (_) {}
  }
  function ready() {
    pending = null;
    clearTimeout(timer);
    processing.hidden = true;
    player.parentElement.hidden = false;
  }
  function remember(state) {
    if (!validId(state.episode_id)) return;
    const row = {episode_id: state.episode_id, robot_id: robot, prompt: state.task || state.prompt || $('prompt')?.value || 'Your latest run', started_at: state.run_started_at || Date.now() / 1000};
    saved = [row, ...saved.filter(item => item.episode_id !== row.episode_id)].slice(0, 100);
    persist();
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
        body: JSON.stringify({email, episode_ids: saved.map(row => row.episode_id), offset})});
      if (!response.ok) throw new Error('Could not load your runs. Try searching again.');
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
        ? (email ? 'Showing runs from this browser and the searched email.' : 'Showing runs from this browser.')
        : (email ? 'No published runs found for this browser or email.' : 'No runs from this browser yet. Search an email to find earlier runs.');
    } catch (error) {
      if (scope === generation && version === searchVersion) $('myRunsStatus').textContent = error.message;
    }
  }
  function openEpisode(id, known = {}) {
    if (!validId(id) || !robot) return;
    ready();
    pending = {id, robot, generation};
    $('past-runs').scrollIntoView({behavior: 'smooth', block: 'start'});
    player.pause(); player.yamRecordingView?.(); player.yamRecordingView = null;
    player.removeAttribute('src'); player.load(); player.parentElement.hidden = true;
    processing.hidden = false;
    if ($('pastRunSpeed')) $('pastRunSpeed').hidden = true;
    $('pastRunTitle').textContent = 'Your run';
    $('pastRunPrompt').textContent = known.prompt || '';
    $('pastRunDetails').textContent = '';
    $('pastRunError').textContent = '';
    $('pastRunMetricsSummary').textContent = '';
    $('pastRunMetricsChart').replaceChildren();
    $('aspirePastLineage')?.remove();
    if (!dialog.open) dialog.showModal();
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
      if (run && run.video_duration_s !== 0 && run.video_url) {
        processingRuns.delete(run.episode_id);
        window.yamReplayHistory.openRun(run);
        loadMine(); window.yamReplayHistory.refresh();
        return;
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
    token = csrf;
    if (!robot) robot = selectedRobot;
    if (robot !== selectedRobot) return;
    const sid = state.session_id;
    if (sid && ['queued', 'preparing', 'running'].includes(state.status)) {
      activeSessions.add(sid); remember(state);
    }
    if (sid && activeSessions.has(sid) && terminal.has(state.status) && validId(state.episode_id) && !completedSessions.has(sid)) {
      completedSessions.add(sid); remember(state); processingRuns.add(state.episode_id);
      const enteredEmail = $('email')?.value.trim();
      if (enteredEmail) { email = enteredEmail; $('runHistoryEmail').value = email; $('clearRunHistoryEmail').hidden = false; }
      openEpisode(state.episode_id, saved[0]); loadMine();
    }
    if (processingRuns.size && token && Date.now() - lastMineAt > 10000) loadMine();
    if (!$('myRunsList').dataset.loaded && token) { $('myRunsList').dataset.loaded = 'true'; loadMine(); }
  }
  window.yamReplayReview = {observe, openEpisode, ready};
  dialog.addEventListener('close', ready);
  $('runHistorySearch').addEventListener('submit', event => {
    event.preventDefault(); email = $('runHistoryEmail').value.trim();
    $('clearRunHistoryEmail').hidden = !email; loadMine();
  });
  $('clearRunHistoryEmail').addEventListener('click', () => {
    email = ''; $('runHistoryEmail').value = ''; $('clearRunHistoryEmail').hidden = true; loadMine();
  });
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
