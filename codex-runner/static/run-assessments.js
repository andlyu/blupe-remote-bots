/* Human labels and revision-scoped reviews; no machine outcome inference. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('liveAssessment')) return;
  let token = '', robot = '', generation = 0, live = null, replay = null, busy = false;
  const active = new Set(['queued', 'preparing', 'running']);
  const empty = () => ({revision:0,label:null,correct:0,incorrect:0,eligibility:'unlabeled',can_edit:false,can_vote:false,history:[]});
  const issued = new Map();
  let requestSequence = 0;
  const groups = ['liveAssessmentControls','replayAssessmentControls','replayVoteControls'];
  function render() {
    for (const [target, scope] of [['live',live],['replay',replay]]) {
      const data = scope?.assessment || empty(), controls = $(target+'AssessmentControls');
      controls.hidden = target === 'replay' && !data.can_edit;
      for (const button of controls.querySelectorAll('button')) {
        button.disabled = busy || !scope?.id || !data.can_edit;
        button.setAttribute('aria-pressed', String((button.dataset.label || null) === data.label));
      }
      if (target === 'replay') {
        $('replayAssessmentSummary').textContent = `${data.label || 'Not completed'} · ${data.correct} correct / ${data.incorrect} incorrect · ${data.eligibility === 'included' ? 'Included in score' : data.eligibility === 'excluded' ? 'Excluded from score; original label retained' : data.eligibility === 'provisional' ? 'Provisional — run in progress' : 'Unlabeled — not scored'}`;
        $('replayVoteControls').hidden = !data.can_vote;
        for (const button of $('replayVoteControls').querySelectorAll('button')) {
          button.disabled = busy || !data.can_vote || (!button.dataset.vote && data.my_vote == null);
          button.setAttribute('aria-pressed', String(!!button.dataset.vote && Number(button.dataset.vote) === data.my_vote));
        }
        $('assessmentHistory').replaceChildren(...(data.history || []).map(row => {
          const li = document.createElement('li');
          li.textContent = `Revision ${row.revision}: ${row.label || 'Not completed'} · ${row.correct} correct / ${row.incorrect} incorrect · ${new Date(row.created_at*1000).toLocaleString()}`;
          return li;
        }));
      }
    }
  }
  async function request(scope, fields = {}) {
    const currentGeneration = generation;
    if (!token || !scope?.id) return;
    const sequence = ++requestSequence; issued.set(scope.id, sequence);
    const response = await fetch('/api/run-assessment', {method:'POST', credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','X-YAM-Runner-Token':token,'X-Blupe-Robot':robot},
      body:JSON.stringify({episode_id:scope.id,...fields})});
    const data = await response.json();
    if (currentGeneration !== generation || issued.get(scope.id) !== sequence) return;
    if (!response.ok) throw new Error(data.error || 'Assessment could not be saved. Try again.');
    for (const value of [live,replay]) if (value?.id === scope.id) value.assessment = data;
    render(); return data;
  }
  async function refresh(scope, force = false) {
    if (busy && !force) return;
    try { await request(scope); }
    catch(error) { if (scope === replay) $('replayAssessmentStatus').textContent = error.message; }
  }
  async function mutate(scope, fields, target) {
    if (busy || !scope?.id) return;
    busy = true; render(); $(target+'AssessmentStatus').textContent = 'Saving…';
    try {
      await request(scope, {...fields,revision:scope.assessment?.revision || 0});
      $(target+'AssessmentStatus').textContent = 'Saved. You can change this later.';
      window.dispatchEvent(new CustomEvent('yam-assessment-changed', {detail:scope.id}));
    } catch(error) {
      $(target+'AssessmentStatus').textContent = error.message;
      await refresh(scope, true);
    } finally { busy = false; render(); }
  }
  for (const id of groups) $(id).addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    const target = id === 'liveAssessmentControls' ? 'live' : 'replay';
    mutate(target === 'live' ? live : replay, id === 'replayVoteControls'
      ? {operation:'vote',vote:button.dataset.vote ? Number(button.dataset.vote) : null}
      : {operation:'assess',label:button.dataset.label || null}, target);
  });
  window.yamRunAssessment = {
    showReplay(run) {
      replay = {id:run.episode_id,assessment:run.assessment || empty()};
      $('replayAssessmentStatus').textContent = 'Review whether the runner’s label is correct. Votes apply to this assessment revision.';
      render(); refresh(replay);
    },
    observe(state, selectedRobot, csrf) {
      if (csrf !== token || selectedRobot !== robot) {
        token = csrf; robot = selectedRobot; generation++; live = null;
        if (replay) refresh(replay);
      }
      const visible = !!state.session_id && (active.has(state.status) || !!state.episode_id);
      $('liveAssessment').hidden = !visible;
      if (!visible) return;
      const changed = live?.id !== state.episode_id || live?.status !== state.status;
      if (changed) {
        live = {id:state.episode_id,status:state.status,assessment:live?.id === state.episode_id ? live.assessment : empty()};
        $('liveAssessmentStatus').textContent = !state.episode_id ? 'Assessment will be available once the recording starts.' : active.has(state.status) ? 'Your label is provisional until the run ends.' : 'Your run ended. You can edit this assessment now or in replay details.';
        render(); refresh(live);
      }
    }
  };
  render();
})();
