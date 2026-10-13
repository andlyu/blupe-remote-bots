/* Remote USB microphone playback. Uses the pinned MediaMTX1.21 WHEP reader.
 * No microphone permission is requested from the viewer's browser.
 */
function createRobotAudio({audio, button, status, createReader, streamFor}) {
  let robot = '', reader = null, generation = 0, enabled = false;
  const supported = () => Boolean(streamFor(robot));
  function stop() {
    generation++;
    enabled = false;
    audio.muted = true;
    audio.pause();
    reader?.close(); reader = null;
    audio.srcObject?.getTracks().forEach(track => track.stop());
    audio.srcObject = null;
    button.textContent = 'Listen';
    button.setAttribute('aria-pressed', 'false');
    button.disabled = !supported();
    status.textContent = supported() ? 'Robot audio off' : 'Robot audio unavailable';
  }
  async function play(token) {
    try {
      await audio.play();
      if (token === generation && enabled) status.textContent = 'Robot audio live';
    } catch (_) {
      if (token === generation && enabled) {
        stop(); status.textContent = 'Playback blocked. Click Listen to retry.';
      }
    }
  }
  function toggle() {
    if (enabled) return stop();
    const path = streamFor(robot);
    if (!path) return;
    enabled = true;
    const token = ++generation;
    button.textContent = 'Mute';
    button.setAttribute('aria-pressed', 'true');
    status.textContent = 'Connecting audio…';
    audio.muted = false;
    try {
      reader = createReader(path, {
        onTrack(event) {
          if (token !== generation || !enabled) { event.track.stop(); return; }
          if (event.track.kind !== 'audio') return;
          audio.srcObject = event.streams[0];
          event.track.onended = () => {
            if (token === generation && enabled) status.textContent = 'Audio interrupted; reconnecting…';
          };
          play(token);
        },
        onError() {
          if (token === generation && enabled) status.textContent = 'Audio unavailable; retrying…';
        }
      });
    } catch (_) {
      stop(); status.textContent = 'Audio unavailable. Click Listen to retry.';
    }
  }
  button.addEventListener('click', toggle);
  return {
    select(value) { if (value !== robot) { stop(); robot = value; stop(); } },
    refresh: stop,
    stop
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
    let streams = {};
    const control = createRobotAudio({audio, button, status,
      streamFor: robot => window.MediaMTXWebRTCReader && window.RTCPeerConnection && streams[robot],
      createReader: (path, callbacks) => new MediaMTXWebRTCReader({
        url: new URL('/' + path + '/whep', location.href).href, ...callbacks
      })
    });
    control.select(window.yamApplication?.defaultRobot || new URLSearchParams(location.search).get('robot_id') || 'yam-1');
    window.addEventListener('blupe-robot-selected', event => control.select(event.detail));
    document.addEventListener('visibilitychange', () => { if (document.hidden) control.stop(); });
    window.addEventListener('pagehide', () => control.stop());
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
