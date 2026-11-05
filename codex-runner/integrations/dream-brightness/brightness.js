(() => {
  'use strict';
  let brightness = 50;
  const previousApplication = window.yamApplication || {};
  window.yamApplication = {
    ...previousApplication,
    async sessionReady(session, context) {
      await previousApplication.sessionReady?.(session, context);
      const name = document.querySelector('#runnerName');
      if (name && ['Local runner', 'Anonymous'].includes(name.value)) name.value = '';
      if (name && !name.value && session.runner_identity?.name) name.value = session.runner_identity.name;
      if (name) {name.placeholder = 'Your real name'; name.required = true;}
      const email = document.querySelector('#email');
      if (email && !email.value && session.runner_identity?.email) email.value = session.runner_identity.email;
      if (email) email.required = true;
      const label = document.querySelector('label[for="email"]');
      if (label) label.textContent = 'Email for run attribution';
      const help = document.querySelector('#emailHelp');
      if (help) help.textContent = 'Used by the existing robot queue for attribution. Kept out of public experiment metadata.';
      document.title = session.local_runner ? 'Dream1 brightness · Local experiment' : 'Dream1 brightness · Experiment';
      panel.querySelector('#brightnessHostingLabel').textContent = session.local_runner ? 'Local experiment' : 'Brightness experiment';
      displayAllowance(session.experiment_allowance);
      mountMeetingControl();
      await selectedCalibration();
    }
  };
  const fetchOriginal = window.fetch.bind(window);
  function displayAllowance(allowance) {
    const label = panel.querySelector('#brightnessAllowance');
    label.hidden = !allowance;
    if (allowance) label.textContent = `${allowance.remaining} of ${allowance.limit} guest runs remaining in this browser.`;
  }
  let connectionNotice;
  let runCalibration = null;
  let selectedProfileText = 'Checking the operator’s selected calibration…';
  function displayCalibration() {
    panel.querySelector('#brightnessCalibration').textContent = runCalibration?.model_calibration_id ?
      `Run calibration: ${runCalibration.model_calibration_id.slice(0,12)} · camera ${runCalibration.camera_calibration_id.slice(0,12)}. Bound for this run; changing profiles requires a new run.` : selectedProfileText;
  }
  async function selectedCalibration() {
    const robot = document.querySelector('#robotSelector')?.value;
    selectedProfileText = 'Checking the operator’s selected calibration…';
    displayCalibration();
    try {
      const response = await fetchOriginal(`/experiment/calibration?robot_id=${encodeURIComponent(robot)}`, {cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Selected calibration unavailable. Check the operator dashboard before Run.');
      if (robot !== document.querySelector('#robotSelector')?.value) return;
      selectedProfileText = data.selected ? `Last checked model calibration: ${data.selected.model_calibration_id.slice(0,12)} · camera ${data.selected.camera_calibration_id.slice(0,12)}. Each new run binds and rechecks the operator’s selection.` : data.note;
    } catch (error) {selectedProfileText = error.message;}
    displayCalibration();
  }
  function showConnectionState(state) {
    if (!connectionNotice) return;
    const busy = ['queued', 'preparing', 'running'].includes(state.status);
    const failed = String(state.error || '').includes('Dream request failed (DreamProtocolError; connection_failure') ||
      state.public_run?.experiment_failure_category === 'model_transport';
    connectionNotice.hidden = busy || !failed;
    connectionNotice.textContent = failed ? 'Dream connection interrupted before the prediction completed. This attempt is excluded from brightness success rates. Check the Dream connection and station readiness before starting a new run.' : '';
    runCalibration = state.run_configuration?.kinematic_calibration || state.public_run?.kinematic_calibration || null;
    displayCalibration();
  }
  const panel = document.createElement('section');
  panel.className = 'brightnessExperiment';
  panel.setAttribute('aria-labelledby', 'brightnessTitle');
  panel.innerHTML = `
    <div class="brightnessHeading"><h2 id="brightnessTitle">Dream1 image brightness</h2><span id="brightnessHostingLabel">Brightness experiment</span></div>
    <p id="brightnessAllowance" role="status" hidden></p>
    <div class="brightnessControls">
      <label for="imageBrightness">Brightness sent to Dream1</label>
      <input id="imageBrightness" type="range" min="0" max="200" step="1" value="50" aria-describedby="brightnessHelp">
      <output id="brightnessValue" for="imageBrightness">50%</output>
      <button type="button" id="brightnessDark">50% darker</button>
      <button type="button" id="brightnessBaseline">100% baseline</button>
    </div>
    <p id="brightnessHelp">All three policy cameras use 50% brightness. Fixed for each run; changes apply to the next run. Live viewing stays at its original brightness.</p>
    <details id="brightnessPreview"><summary>Preview the images sent to Dream1</summary>
      <div class="brightnessPreviewControls"><button type="button" id="refreshBrightnessPreview">Refresh preview</button><p id="brightnessPreviewStatus" role="status">Open to capture a fresh preview of all three inputs.</p></div>
      <div id="brightnessFrames" class="brightnessFrames"></div>
    </details>
    <p id="brightnessRunSetting" role="status">Next run: 50% brightness.</p>
    <p id="brightnessCalibration" role="status">New runs bind the operator’s selected calibration before joining the queue.</p>
    <details id="brightnessResults"><summary>Relative performance</summary>
      <div class="brightnessPreviewControls"><button type="button" id="refreshBrightnessResults">Refresh results</button><p id="brightnessResultsStatus" role="status">Compare reviewed 100% and 50% trials of the same task.</p></div>
      <div id="brightnessResultsBody"></div>
    </details>`;
  function mountMeetingControl() {
    // The current shared UI moves its original camera/composer nodes into a
    // full-height room. Keep the experiment reachable beside its Run controls.
    if (!document.querySelector('#meetingWorkspace') || document.querySelector('#brightnessOpen')) return;
    const toolbar = document.querySelector('#composerSettings')?.parentElement;
    if (!toolbar) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'brightnessDialog'; dialog.className = 'brightnessDialog';
    dialog.setAttribute('aria-labelledby', 'brightnessTitle');
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'brightnessClose';
    close.textContent = 'Close image settings';
    close.addEventListener('click', () => dialog.close());
    dialog.append(close, panel); document.body.append(dialog);
    const open = document.createElement('button');
    open.type = 'button'; open.id = 'brightnessOpen';
    open.textContent = `Inputs ${brightness}%`;
    open.setAttribute('aria-label', `Image brightness: ${brightness}%`);
    open.setAttribute('aria-haspopup', 'dialog');
    open.setAttribute('aria-controls', 'brightnessDialog');
    open.addEventListener('click', () => dialog.showModal());
    toolbar.prepend(open);
  }
  const insert = () => {
    const target = document.querySelector('.watchLayout');
    if (target) target.before(panel);
    else document.querySelector('main').prepend(panel);
    connectionNotice = document.createElement('p');
    connectionNotice.id = 'dreamConnectionNotice';
    connectionNotice.className = 'dreamConnectionNotice';
    connectionNotice.hidden = true;
    connectionNotice.setAttribute('role', 'status');
    document.querySelector('#message')?.after(connectionNotice);
    const slider = panel.querySelector('#imageBrightness');
    const update = value => {
      brightness = Number(value);
      slider.value = brightness;
      panel.querySelector('#brightnessValue').value = `${brightness}%`;
      panel.querySelector('#brightnessHelp').textContent = `All three policy cameras use ${brightness}% brightness. Fixed for each run; changes apply to the next run. Live viewing stays at its original brightness.`;
      panel.querySelector('#brightnessRunSetting').textContent = `Next run: ${brightness}% brightness${brightness === 100 ? ' (baseline)' : ''}.`;
      const open = document.querySelector('#brightnessOpen');
      if (open) {open.textContent = `Inputs ${brightness}%`; open.setAttribute('aria-label', `Image brightness: ${brightness}%`);}
      panel.querySelector('#brightnessFrames').replaceChildren();
      panel.querySelector('#brightnessPreviewStatus').textContent = 'Setting changed. Refresh to see the new input brightness.';
    };
    slider.addEventListener('input', () => update(slider.value));
    panel.querySelector('#brightnessDark').addEventListener('click', () => update(50));
    panel.querySelector('#brightnessBaseline').addEventListener('click', () => update(100));
    let pending = false;
    async function preview() {
      if (pending) return;
      const value = brightness;
      const robot = document.querySelector('#robotSelector')?.value || 'robot-ba8413962083809c';
      const status = panel.querySelector('#brightnessPreviewStatus');
      const button = panel.querySelector('#refreshBrightnessPreview');
      pending = true; button.disabled = true;
      status.textContent = 'Capturing overhead and both wrist cameras…';
      try {
        const response = await fetchOriginal(`/experiment/preview?brightness=${value / 100}&robot_id=${encodeURIComponent(robot)}`, {cache:'no-store'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Preview failed. Refresh to try again.');
        if (value !== brightness || robot !== document.querySelector('#robotSelector')?.value) return;
        const frames = data.frames.map(frame => {
          const figure = document.createElement('figure');
          const image = document.createElement('img');
          const caption = document.createElement('figcaption');
          const label = {top:'Overhead',left:'Left wrist',right:'Right wrist'}[frame.camera];
          image.src = `data:image/jpeg;base64,${frame.jpeg}`;
          image.alt = `${label} policy input at ${value}% brightness`;
          image.width = 320; image.height = 176;
          caption.textContent = `${label} · ${value}%`;
          figure.append(image, caption);
          return figure;
        });
        panel.querySelector('#brightnessFrames').replaceChildren(...frames);
        status.textContent = 'Fresh preview · 320 × 176 JPEG. Inference uses fresh frames captured during the run.';
      } catch (error) {
        status.textContent = error.message;
      } finally {
        pending = false; button.disabled = false;
      }
    }
    panel.querySelector('#refreshBrightnessPreview').addEventListener('click', preview);
    panel.querySelector('#brightnessPreview').addEventListener('toggle', event => {if (event.target.open) preview();});
    let resultsPending = false;
    async function results() {
      if (resultsPending) return;
      resultsPending = true;
      const button = panel.querySelector('#refreshBrightnessResults');
      const status = panel.querySelector('#brightnessResultsStatus');
      button.disabled = true;
      status.textContent = 'Reading recorded trial conditions and reviewed outcomes…';
      const robot = document.querySelector('#robotSelector')?.value || 'robot-ba8413962083809c';
      try {
        const response = await fetchOriginal(`/experiment/results?robot_id=${encodeURIComponent(robot)}`, {cache:'no-store'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Results unavailable. Refresh to try again.');
        if (robot !== document.querySelector('#robotSelector')?.value) return;
        const body = panel.querySelector('#brightnessResultsBody');
        body.replaceChildren();
        for (const group of data.groups) {
          const section = document.createElement('section');
          const heading = document.createElement('p');
          heading.textContent = `${group.task} · ${group.model} · ${group.duration_s}s`;
          if (group.model_calibration_id) heading.textContent += ` · calibration ${group.model_calibration_id.slice(0,12)}`;
          const table = document.createElement('table');
          const caption = document.createElement('caption');
          caption.textContent = 'Reviewed task outcomes by input brightness';
          table.append(caption);
          const header = document.createElement('tr');
          for (const title of ['Brightness', 'Runs', 'Scored', 'Connection failures', 'Success rate']) {
            const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = title; header.append(cell);
          }
          const head = document.createElement('thead'); head.append(header); table.append(head);
          const rows = document.createElement('tbody');
          for (const variant of group.variants) {
            const row = document.createElement('tr');
            const rate = variant.success_rate === null ? 'Not scored' : `${(variant.success_rate * 100).toFixed(0)}% (${variant.successes}/${variant.scored})`;
            for (const text of [`${variant.brightness_percent}%`, variant.runs, variant.scored, variant.connection_failures || 0, rate]) {
              const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
            }
            rows.append(row);
          }
          table.append(rows);
          const difference = document.createElement('p');
          const points = group.difference_percentage_points;
          difference.textContent = points === null ? '50% vs 100%: both conditions need reviewed outcomes.' :
            `50% vs 100%: ${points >= 0 ? '+' : ''}${points.toFixed(1)} percentage points. Descriptive comparison; scene differences can affect the result.`;
          section.append(heading, table, difference); body.append(section);
        }
        status.textContent = data.warning || (data.runs ? data.note : 'No experiment runs yet. Run a 100% baseline and a 50% trial, review each replay, and mark Succeeded or Failed. Restore the same scene between trials.');
      } catch (error) {
        status.textContent = error.message;
      } finally {
        resultsPending = false; button.disabled = false;
      }
    }
    panel.querySelector('#refreshBrightnessResults').addEventListener('click', results);
    panel.querySelector('#brightnessResults').addEventListener('toggle', event => {if (event.target.open) results();});
    document.querySelector('#robotSelector')?.addEventListener('change', () => {
      runCalibration = null;
      selectedCalibration();
      panel.querySelector('#brightnessFrames').replaceChildren();
      panel.querySelector('#brightnessPreviewStatus').textContent = 'Robot changed. Refresh to preview its camera inputs.';
      panel.querySelector('#brightnessResultsBody').replaceChildren();
      panel.querySelector('#brightnessResultsStatus').textContent = 'Robot changed. Refresh to compare its trials.';
    });
  };
  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin && url.pathname === '/api/run' && options?.body) {
      const payload = JSON.parse(options.body);
      payload.image_brightness = brightness / 100;
      const selected = brightness;
      const response = await fetchOriginal(input, {...options, body:JSON.stringify(payload)});
      if (response.ok) panel.querySelector('#brightnessRunSetting').textContent = `Submitted run: ${selected}% brightness. This setting is recorded with the run.`;
      try {const state = await response.clone().json(); if (state.experiment_allowance) displayAllowance(state.experiment_allowance);} catch (_) {}
      return response;
    }
    const response = await fetchOriginal(input, options);
    if (url.origin === location.origin && url.pathname === '/api/status' && response.ok) {
      const robot = document.querySelector('#robotSelector')?.value;
      try {
        const state = await response.clone().json();
        if (robot === document.querySelector('#robotSelector')?.value) showConnectionState(state);
      } catch (_) { /* Preserve the original response and native status handling. */ }
    }
    return response;
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', insert);
  else insert();
})();
