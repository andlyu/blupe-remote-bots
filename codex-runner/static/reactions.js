/* Ephemeral screen reactions. Delivery uses the visitor chat poll, never its log. */
function createPlaygroundReactions(document, schedule = setTimeout, cancel = clearTimeout) {
  const dock = document.getElementById('reactionDock');
  if (!dock) return null;
  const stage = document.getElementById('reactionStage');
  const status = document.getElementById('reactionStatus');
  const buttons = Array.from(dock.querySelectorAll('[data-reaction]'));
  const labels = new Map(buttons.map(button => [button.dataset.reaction, button.dataset.label]));
  const seen = new Set(), timers = new Set();
  let send, available = false, busy = false, baseline = 0, generation = 0;
  function update() { buttons.forEach(button => { button.disabled = !available || busy; }); }
  function later(fn, ms) {
    const timer = schedule(() => { timers.delete(timer); fn(); }, ms);
    timers.add(timer); return timer;
  }
  function receive(events = []) {
    for (const event of events) {
      if (!Number.isSafeInteger(event.id) || event.id <= baseline || seen.has(event.id) ||
          !labels.has(event.emoji) || !Number.isFinite(event.remaining_ms)) continue;
      seen.add(event.id);
      // Suppress stale events and background-tab bursts. The server's relative
      // lifetime also avoids relying on visitors having synchronized clocks.
      if (document.hidden || event.remaining_ms < 2500) continue;
      const popup = document.createElement('span');
      popup.className = 'reactionPopup'; popup.textContent = event.emoji;
      popup.setAttribute('aria-hidden', 'true');
      stage.append(popup);
      while (stage.children.length > 6) stage.firstElementChild.remove();
      later(() => popup.remove(), Math.min(2400, event.remaining_ms));
      status.classList.remove('reactionError');
      status.textContent = labels.get(event.emoji) + ' reaction';
    }
    // At most 128 live events can exist on the server.
    while (seen.size > 256) seen.delete(seen.values().next().value);
  }
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (!available || busy || !send) return;
    const version = generation;
    busy = true; update(); status.textContent = '';
    try {
      const result = await send(button.dataset.reaction);
      if (version !== generation) return;
      receive([result.reaction]);
    } catch (error) {
      if (version !== generation || error.stale) return;
      status.textContent = error.message || 'Reaction could not be sent. Try again.';
      status.classList.add('reactionError');
    } finally {
      if (version === generation) later(() => { busy = false; update(); }, 1000);
    }
  }));
  document.addEventListener('visibilitychange', () => {
    stage.replaceChildren();
    status.textContent = '';
  });
  return {
    configure(sender) { send = sender; },
    setAvailable(value) { available = value; update(); },
    reset(cursor = 0) {
      generation++; baseline = cursor; seen.clear(); busy = false;
      timers.forEach(cancel); timers.clear();
      stage.replaceChildren(); status.textContent = ''; status.classList.remove('reactionError'); update();
    },
    receive,
  };
}
if (typeof module !== 'undefined') module.exports = {createPlaygroundReactions};
if (typeof window !== 'undefined') window.yamReactions = createPlaygroundReactions(document);
