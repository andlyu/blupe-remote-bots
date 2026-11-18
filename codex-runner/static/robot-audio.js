/* Audio is played by the SAME media element as the camera composite.
 * This preserves A/V timing through WebRTC and HLS, including stalls/seeks.
 * Browser policy: docs/refs/browser-audio/INDEX.md. No browser microphone input.
 */
function createRobotAudio({button, status, streamFor, enabled = false,
  visible = true, remember = () => {}}) {
  let robot = '', media = null, hasAudio = false, wanted = enabled;
  let generation = 0, needsAction = null;
  const supported = () => Boolean(streamFor(robot));
  function render(message, live = false) {
    button.textContent = needsAction === 'blocked' ? 'Enable audio' : needsAction === 'error' ? 'Retry audio' : wanted ? 'Mute' : 'Unmute';
    button.setAttribute('aria-label', button.textContent + ' for selected robot microphone');
    button.setAttribute('aria-pressed', String(live));
    button.disabled = !supported();
    status.textContent = message;
  }
  function detach(video = media) {
    if (video !== media) return;
    generation++;
    if (media) media.muted = true;
    media = null; hasAudio = false; needsAction = null;
    render(wanted ? 'Waiting for robot audio' : 'Robot audio muted');
  }
  function apply() {
    const token = ++generation, target = media, stream = media?.srcObject;
    needsAction = null;
    if (target) target.muted = true;
    if (!supported()) return render('Robot audio unavailable');
    if (!wanted) return render('Robot audio muted');
    if (!visible) return render('Robot audio paused');
    if (!target || !hasAudio) return render('Waiting for robot audio');
    const current = () => token === generation && target === media &&
      target.srcObject === stream && visible && wanted;
    target.muted = false;
    render('Starting audio…');
    // Invoke play in the click handler itself when autoplay previously failed.
    Promise.resolve(target.play()).then(() => {
      if (current()) render('Robot audio live', true);
    }).catch(error => {
      if (!current()) return;
      target.muted = true;
      needsAction = error.name === 'NotAllowedError' ? 'blocked' : 'error';
      render(needsAction === 'blocked' ? 'Audio needs a click' : 'Audio unavailable');
      // Rejected audible autoplay must never interrupt the muted camera view.
      target.play().catch(() => {});
    });
  }
  function setEnabled(value) { wanted = value; apply(); }
  button.addEventListener('click', () => {
    const value = needsAction ? true : !wanted;
    remember(value); setEnabled(value);
  });
  return {
    select(value) { if (value !== robot) { detach(); robot = value; apply(); } },
    attach(video, selectedRobot, path, available) {
      if (selectedRobot !== robot || path !== streamFor(robot)) { video.muted = true; return; }
      if (media === video && hasAudio === available) return;
      detach(); media = video; hasAudio = available; apply();
    },
    detach,
    refresh: apply,
    setEnabled,
    setVisible(value) { if (visible !== value) { visible = value; apply(); } }
  };
}

if (typeof module !== 'undefined') module.exports = {createRobotAudio};
if (typeof window !== 'undefined') {
  const host = document.getElementById('videoDelayNotice');
  if (host) {
    const button = document.createElement('button'), status = document.createElement('span');
    button.type = 'button'; button.id = 'robotAudioToggle'; button.className = 'robotAudioToggle';
    status.id = 'robotAudioStatus'; status.setAttribute('role', 'status');
    host.append(' ', button, ' ', status);
    let streams = {}, enabled = false;
    const preferenceKey = 'blupe-robot-audio';
    try { enabled = localStorage.getItem(preferenceKey) === 'enabled'; } catch (_) {}
    const control = createRobotAudio({button, status, enabled, visible:!document.hidden,
      streamFor: robot => streams[robot],
      remember: value => { try { localStorage.setItem(preferenceKey, value ? 'enabled' : 'muted'); } catch (_) {} }
    });
    window.yamRobotAudio = control;
    control.select(window.yamApplication?.defaultRobot || new URLSearchParams(location.search).get('robot_id') || 'yam-1');
    window.addEventListener('blupe-robot-selected', event => control.select(event.detail));
    document.addEventListener('visibilitychange', () => control.setVisible(!document.hidden));
    window.addEventListener('pagehide', () => control.setVisible(false));
    window.addEventListener('pageshow', () => control.setVisible(!document.hidden));
    window.addEventListener('storage', event => {
      if (event.key === preferenceKey) control.setEnabled(event.newValue === 'enabled');
    });
    fetch('/synchronized/audio-config.json', {cache:'no-store', credentials:'same-origin', signal:AbortSignal.timeout(5000)})
      .then(response => response.ok ? response.json() : null).then(config => {
        if (config?.version !== 2 || !config.streams || typeof config.streams !== 'object') return;
        streams = Object.fromEntries(Object.entries(config.streams).filter(([robot, path]) =>
          /^[a-z0-9][a-z0-9_-]{0,63}$/.test(robot) && typeof path === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(path)));
        control.refresh();
        // Metadata may arrive after the camera's first track/manifest event.
        window.dispatchEvent(new Event('blupe-audio-configured'));
      }).catch(() => control.refresh());
  }
}
