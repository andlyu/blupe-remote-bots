/* Remote USB microphone playback. Uses the pinned MediaMTX1.21 WHEP reader.
 * Browser policy reference: docs/refs/browser-audio/INDEX.md.
 * No microphone permission is requested from the viewer's browser.
 */
function createRobotAudio({audio, button, status, createReader, streamFor,
  enabled = true, visible = true, remember = () => {}}) {
  let robot = '', reader = null, generation = 0, playAttempt = 0;
  let wanted = enabled, needsAction = null;
  const supported = () => Boolean(streamFor(robot));
  function render(message, live = false) {
    button.textContent = needsAction === 'blocked' ? 'Enable audio' : needsAction === 'error' ? 'Retry audio' : wanted ? 'Mute' : 'Unmute';
    button.setAttribute('aria-label', button.textContent + ' for selected robot microphone');
    button.setAttribute('aria-pressed', String(live));
    button.disabled = !supported();
    status.textContent = message;
  }
  function clearMedia() {
    playAttempt++;
    audio.muted = true;
    audio.pause();
    audio.srcObject?.getTracks().forEach(track => track.stop());
    audio.srcObject = null;
  }
  function disconnect() {
    generation++;
    reader?.close(); reader = null;
    clearMedia();
    needsAction = null;
  }
  async function play(token) {
    const stream = audio.srcObject, attempt = ++playAttempt;
    const current = () => token === generation && attempt === playAttempt &&
      wanted && visible && audio.srcObject === stream;
    audio.muted = false;
    needsAction = null;
    render('Starting audio…');
    try {
      // Called synchronously from the fallback click when the stream is ready.
      await audio.play();
      if (current()) render('Robot audio live', true);
    } catch (error) {
      if (current()) {
        audio.muted = true;
        audio.pause();
        needsAction = error.name === 'NotAllowedError' ? 'blocked' : 'error';
        render(needsAction === 'blocked' ? 'Audio needs a click' : 'Audio unavailable');
      }
    }
  }
  function start() {
    if (!supported()) return render('Robot audio unavailable');
    if (!wanted) return render('Robot audio muted');
    if (!visible) return render('Robot audio paused');
    if (reader) return;
    const token = ++generation;
    render('Connecting audio…');
    try {
      reader = createReader(streamFor(robot), {
        onTrack(event) {
          if (token !== generation || !wanted || !visible) { event.track.stop(); return; }
          if (event.track.kind !== 'audio') return;
          clearMedia();
          const stream = event.streams[0];
          audio.srcObject = stream;
          event.track.onended = () => {
            if (token === generation && audio.srcObject === stream) {
              clearMedia(); needsAction = null; render('Audio interrupted; reconnecting…');
            }
          };
          play(token);
        },
        onError() {
          if (token === generation && wanted && visible) {
            clearMedia(); needsAction = null; render('Audio unavailable; retrying…');
          }
        }
      });
    } catch (_) {
      disconnect(); needsAction = 'error'; render('Audio unavailable');
    }
  }
  function setEnabled(value) {
    wanted = value;
    if (!wanted) { disconnect(); start(); }
    else if (needsAction && audio.srcObject && visible) play(generation);
    else start();
  }
  button.addEventListener('click', () => {
    const value = needsAction ? true : !wanted;
    remember(value);
    setEnabled(value);
  });
  return {
    select(value) {
      if (value !== robot) { disconnect(); robot = value; start(); }
    },
    refresh() { disconnect(); start(); },
    setEnabled,
    setVisible(value) {
      if (visible === value) return;
      visible = value;
      if (!visible) disconnect();
      start();
    }
  };
}

if (typeof module !== 'undefined') module.exports = {createRobotAudio};
if (typeof window !== 'undefined') {
  const host = document.getElementById('videoDelayNotice');
  if (host) {
    const button = document.createElement('button'), status = document.createElement('span');
    const audio = document.createElement('audio');
    button.type = 'button'; button.id = 'robotAudioToggle'; button.className = 'robotAudioToggle';
    button.setAttribute('aria-label', 'Listen to selected robot microphone');
    status.id = 'robotAudioStatus'; status.setAttribute('role', 'status');
    audio.id = 'robotAudio'; audio.muted = true; audio.hidden = true;
    host.append(' ', button, ' ', status, audio);
    let streams = {}, enabled = true;
    const preferenceKey = 'blupe-robot-audio';
    try { enabled = localStorage.getItem(preferenceKey) !== 'muted'; } catch (_) {}
    const control = createRobotAudio({audio, button, status, enabled, visible:!document.hidden,
      remember: value => { try { localStorage.setItem(preferenceKey, value ? 'enabled' : 'muted'); } catch (_) {} },
      streamFor: robot => window.MediaMTXWebRTCReader && window.RTCPeerConnection && streams[robot],
      createReader: (path, callbacks) => new MediaMTXWebRTCReader({
        url: new URL('/' + path + '/whep', location.href).href, ...callbacks
      })
    });
    control.select(window.yamApplication?.defaultRobot || new URLSearchParams(location.search).get('robot_id') || 'yam-1');
    window.addEventListener('blupe-robot-selected', event => control.select(event.detail));
    document.addEventListener('visibilitychange', () => control.setVisible(!document.hidden));
    window.addEventListener('pagehide', () => control.setVisible(false));
    window.addEventListener('pageshow', () => control.setVisible(!document.hidden));
    window.addEventListener('storage', event => {
      if (event.key === preferenceKey) control.setEnabled(event.newValue !== 'muted');
    });
    fetch('/synchronized/audio-config.json', {cache:'no-store', credentials:'same-origin', signal:AbortSignal.timeout(5000)})
      .then(response => response.ok ? response.json() : null).then(config => {
        if (config?.version !== 1 || !config.streams || typeof config.streams !== 'object') return;
        streams = Object.fromEntries(Object.entries(config.streams).filter(([robot, path]) =>
          /^[a-z0-9][a-z0-9_-]{0,63}$/.test(robot) && typeof path === 'string' &&
          /^synchronized\/audio\/[a-z0-9][a-z0-9_-]{0,63}$/.test(path)));
        control.refresh();
      }).catch(() => control.refresh());
  }
}
