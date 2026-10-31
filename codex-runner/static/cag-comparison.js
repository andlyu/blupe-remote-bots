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
        ? 'MolmoAct2 + CAG-inspired guidance' : 'MolmoAct2 baseline';
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
      document.querySelector('.runnerContent').prepend(status);
      document.title = 'Completion Aware Guidance · MolmoAct2 · BluPe';
      const name = document.getElementById('runnerName');
      const email = document.getElementById('email');
      name.value = typeof saved.name === 'string' ? saved.name : (session.research_identity_defaults?.runner_name || '');
      email.value = typeof saved.email === 'string' ? saved.email : (session.research_identity_defaults?.email || '');
      email.required = true;
      const identityHelp = name.parentElement.querySelector('.help');
      if (identityHelp) identityHelp.textContent = 'Your name and task are shown with your run. Your email stays private.';
      document.querySelector('label[for="email"]').textContent = 'Your email';
      document.getElementById('emailHelp').textContent = 'Confirm your name and email for this run. Both fields are editable; email stays private.';
      const provider = document.getElementById('provider');
      for (const option of [...provider.options]) {
        if (!['molmoact_baseline', 'molmoact_guided'].includes(option.value)) option.remove();
      }
      const advanced = document.getElementById('advancedModelOptions');
      if (advanced) advanced.before(controls);
      update();
    },
    stateChanged(state) {
      const progress = window.cagProgress(state, runsEnabled);
      const status = document.getElementById('cagStatus');
      if (status) {
        status.textContent = progress.text;
        status.dataset.phase = progress.phase;
        status.setAttribute('aria-busy', String(progress.phase === 'starting'));
      }
      if (!runsEnabled) {
        document.getElementById('run').disabled = true;
        const notice = document.getElementById('publicRunError');
        if (notice?.textContent.includes('GPU inference is paused')) notice.hidden = true;
      }
    },
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
