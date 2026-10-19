/* Optional application-backed email delivery for the exact viewed replay. */
function createReplayEmailControl({$, send}) {
  const button = $('replayEmailButton'), hint = $('replayEmailHint'), status = $('replayEmailStatus');
  const dialog = $('replayEmailDialog'), form = $('replayEmailForm'), input = $('replayEmailAddress');
  const submit = $('replayEmailSend'), error = $('replayEmailError');
  let enabled = false, selected = null, session = '', latestEmail = '', version = 0;
  let busy = false, timer = null, modalTarget = null;
  const validEmail = value => typeof value === 'string' && /^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/.test(value);
  const identity = row => row ? row.robot_id + ':' + row.episode_id : '';
  const current = (scope, target) => version === scope && identity(selected) === identity(target);
  function sync() {
    button.hidden = !enabled; button.disabled = !enabled || !selected || busy; submit.disabled = busy;
    hint.textContent = enabled && latestEmail ? `Sends to ${latestEmail}` : ''; hint.hidden = !hint.textContent;
  }
  function stopPoll() { clearTimeout(timer); timer = null; }
  function showReceipt(receipt, destination, scope, target) {
    if (!current(scope, target)) return;
    const messages = {
      queued: `Email queued for ${destination}. We’ll send it shortly.`,
      retrying: `Delivery to ${destination} is delayed. We’re retrying.`,
      sent: `Sent to ${destination}. Check your inbox.`,
      failed: 'We couldn’t send this video. Check the address and try again later.'
    };
    status.textContent = messages[receipt.state] || messages.queued;
    if (['queued', 'retrying'].includes(receipt.state)) timer = setTimeout(() => poll(receipt.request_id, destination, scope, target), 3000);
  }
  async function poll(requestId, destination, scope, target) {
    if (!current(scope, target)) return;
    try {
      showReceipt(await send('/api/replay-email/status', {request_id: requestId}), destination, scope, target);
    } catch (err) {
      if (!current(scope, target)) return;
      status.textContent = 'Couldn’t check email delivery. Checking again shortly…';
      timer = setTimeout(() => poll(requestId, destination, scope, target), 5000);
    }
  }
  async function request(target, scope, destination, payload) {
    stopPoll();
    const receipt = await send('/api/replay-email/request', {episode_id: target.episode_id, consent: true, ...payload});
    showReceipt(receipt, destination, scope, target);
  }
  button.addEventListener('click', async () => {
    if (!enabled || !selected || busy) return;
    const target = {...selected}, scope = version;
    busy = true; sync(); status.textContent = 'Preparing your email…';
    try {
      // Session metadata never comes from the replay owner, history, or a form.
      const context = await send('/api/replay-email/context', {});
      if (!current(scope, target)) return;
      if (!context.enabled) throw new Error('Video email is temporarily unavailable.');
      latestEmail = validEmail(context.session_email) ? context.session_email : '';
      if (latestEmail) {
        await request(target, scope, latestEmail, {use_session_email: true, session_email: latestEmail});
      } else {
        status.textContent = ''; modalTarget = {target, scope}; input.value = ''; error.textContent = '';
        dialog.showModal(); input.focus();
      }
    } catch (err) {
      if (current(scope, target)) status.textContent = err.message || 'Couldn’t queue this email. Please try again.';
    } finally {
      if (current(scope, target)) { busy = false; sync(); }
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!modalTarget || busy || !dialog.open || !form.reportValidity()) return;
    const {target, scope} = modalTarget, destination = input.value.trim();
    if (!current(scope, target)) return;
    busy = true; error.textContent = ''; sync();
    try {
      await request(target, scope, destination, {email: destination});
      if (current(scope, target)) dialog.close();
    } catch (err) {
      if (current(scope, target)) error.textContent = err.message || 'Couldn’t queue this email. Please try again.';
    } finally {
      if (current(scope, target)) { busy = false; sync(); }
    }
  });
  $('replayEmailCancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { modalTarget = null; });
  const control = {
    configure(config, key) {
      if (session !== key) {
        version++; busy = false; stopPoll(); status.textContent = ''; modalTarget = null;
        if (dialog.open) dialog.close();
      }
      session = key; enabled = config?.enabled === true;
      latestEmail = enabled && validEmail(config.session_email) ? config.session_email : ''; sync();
    },
    setRun(run) {
      const next = run && /^ep_[A-Za-z0-9_-]{1,100}$/.test(run.episode_id || '') && run.video_url
        ? {episode_id: run.episode_id, robot_id: run.robot_id} : null;
      if (identity(next) !== identity(selected)) {
        version++; busy = false; stopPoll(); status.textContent = ''; modalTarget = null;
        if (dialog.open) dialog.close();
      }
      selected = next; sync();
    }
  };
  $('pastRunDialog').addEventListener('close', () => control.setRun(null));
  sync(); return control;
}
