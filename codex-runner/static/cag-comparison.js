/* Loaded only by the MolmoAct2 comparison launcher. */
(() => {
  'use strict';
  let runsEnabled = true;
  const savedIdentityKey = 'blupe-cag-runner';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(savedIdentityKey) || '{}'); } catch (_) {}
  const help = document.getElementById('policyHelp');
  const controls = document.createElement('fieldset');
  controls.id = 'cagControls';
  controls.innerHTML = `<legend>Completion-aware guidance variant</legend>
    <label for="cagStrength">Guidance strength <output id="cagStrengthValue" for="cagStrength">0.15</output></label>
    <input id="cagStrength" type="range" min="0" max="0.30" step="0.01" value="0.15" aria-describedby="cagStrengthHelp">
    <p id="cagStrengthHelp" class="help">Select the guided policy to adjust strength. Baseline always uses 0. Applies when you press Run.</p>
    <p class="help">Experimental port of the CAG paper to MolmoAct2. Same checkpoint, seed 0 and 10 sampling steps in both modes. YAM1 only. This demo has not established a task-success improvement.</p>`;
  help.after(controls);
  const strength = document.getElementById('cagStrength');
  const value = document.getElementById('cagStrengthValue');
  function update() {
    const guided = document.getElementById('provider').value === 'molmoact_guided';
    strength.disabled = !guided;
    value.value = guided ? Number(strength.value).toFixed(2) : '0.00 (baseline)';
  }
  strength.addEventListener('input', update);
  document.getElementById('provider').addEventListener('change', update);
  window.yamApplication = {
    defaultRobot: 'yam-1',
    selectRobot(robot) { return robot !== 'yam-1'; },
    modelDisplayName() {
      return document.getElementById('provider').value === 'molmoact_guided'
        ? 'MolmoAct2+CAG variant' : 'MolmoAct2 baseline';
    },
    configuredProviderChanged: update,
    sessionReady(session) {
      const station = document.getElementById('robotSelect');
      if (station) station.disabled = true;
      const status = document.createElement('p');
      status.className = 'cagStatus';
      status.id = 'cagStatus';
      status.setAttribute('role', 'status');
      runsEnabled = session.research_integration?.runs_enabled !== false;
      status.textContent = window.cagProgress({}, runsEnabled).text;
      document.getElementById('liveViewer').closest('.videoPanel').after(status);
      document.title = 'Completion Aware Guidance · MolmoAct2 · BluPe';
      const name = document.getElementById('runnerName');
      const email = document.getElementById('email');
      name.value = typeof saved.name === 'string' ? saved.name : (session.research_identity_defaults?.runner_name || '');
      email.value = typeof saved.email === 'string' ? saved.email : (session.research_identity_defaults?.email || '');
      email.required = true;
      const identityHelp = name.parentElement.querySelector('.help');
      if (identityHelp) identityHelp.textContent = 'Your name and task are shown with your run. Your email stays private.';
      document.querySelector('label[for="email"]').textContent = 'Your email';
      document.getElementById('emailHelp').textContent = 'Run confirms these editable details. Your name is shown with the run; email stays private.';
      const identity = document.createElement('div');
      identity.id = 'cagRunnerFields';
      const nameLabel = name.parentElement.querySelector('label');
      const emailLabel = document.querySelector('label[for="email"]');
      name.setAttribute('form','runForm'); email.setAttribute('form','runForm');
      const nameField = document.createElement('div'), emailField = document.createElement('div');
      nameField.append(nameLabel,name); emailField.append(emailLabel,email);
      identity.append(nameField,emailField,document.getElementById('emailHelp'));
      status.before(identity);
      const stages = document.createElement('ol');
      stages.id = 'cagStartupStages';
      stages.setAttribute('aria-label', 'Confirmed startup stages');
      status.after(stages);
      document.getElementById('runDuration').value = '1';
      // Confirm the visible fields with the same normal validated Run action.
      for (const id of ['quickRun','composerSend']) {
        document.getElementById(id).addEventListener('click', event => {
          const form=document.getElementById('runForm');
          if (!runsEnabled || form.classList.contains('runActive')) return;
          event.preventDefault();event.stopImmediatePropagation();
          form.requestSubmit(document.getElementById('run'));
        }, {capture:true});
      }
      document.getElementById('runForm').addEventListener('submit', () => {
        const current=document.getElementById('cagStatus');
        current.textContent=window.cagProgress({status:'preparing',provider:{warmup:'checking',warmup_elapsed_s:0}},runsEnabled).text;
        current.dataset.runClickAt=String(Date.now());
        delete current.dataset.homeCompletedAt;
        document.getElementById('cagStartupStages').replaceChildren();
      }, {capture:true});
      const provider = document.getElementById('provider');
      for (const option of [...provider.options]) {
        if (!['molmoact_baseline', 'molmoact_guided'].includes(option.value)) option.remove();
      }
      const advanced = document.getElementById('advancedModelOptions');
      if (advanced) advanced.before(controls);
      update();
    },
    stateChanged(state) {
      window.cagLiveReplay?.observe(state);
      const progress = window.cagProgress(state, runsEnabled);
      const status = document.getElementById('cagStatus');
      if (status) {
        status.textContent = progress.text;
        status.dataset.phase = progress.phase;
        status.setAttribute('aria-busy', String(['checking','starting','queued','preparing','first_action','finishing'].includes(progress.phase)));
        const stages=document.getElementById('cagStartupStages');
        if (stages) stages.replaceChildren(...progress.stages.map(text => {
          const row=document.createElement('li'); row.textContent=text; return row;
        }));
        const home=state.cag_startup?.home?.completed_at;
        if (home) status.dataset.homeCompletedAt=String(home * 1000);
        const message=document.getElementById('message');
        if (message && ['preparing','queued'].includes(state.status)) message.textContent=progress.text;
        const queue=document.getElementById('yourQueue');
        if (queue && state.status === 'preparing' && !state.session_id) queue.hidden=true;
      }
      if (!runsEnabled) {
        for (const id of ['run', 'quickRun', 'composerSend']) {
          const button = document.getElementById(id);
          if (button) button.disabled = true;
        }
        const notice = document.getElementById('publicRunError');
        if (notice?.textContent.includes('GPU inference is paused')) notice.hidden = true;
      }
    },
    submit() { return !runsEnabled; },
    configureRunPayload(payload) {
      if (payload.provider.startsWith('molmoact_')) {
        payload.guidance_strength = Number(strength.value);
        payload.runner_kind = 'human';
        try { localStorage.setItem(savedIdentityKey, JSON.stringify({name:payload.runner_name,email:payload.email})); } catch (_) {}
      }
    }
  };
  update();
})();
