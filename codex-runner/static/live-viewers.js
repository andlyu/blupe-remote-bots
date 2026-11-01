/* Anonymous, per-robot live audience count; uses the existing status poll. */
(() => {
  function create({badge, label, viewer, doc = document, viewport = window,
                   clock = () => performance.now()}) {
    let receivedAt = null;
    function reset() {
      receivedAt = null;
      if (badge) badge.hidden = true;
    }
    function watching() {
      if (doc.hidden || !viewer?.isConnected) return false;
      const rect = viewer.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0
        && rect.top < viewport.innerHeight && rect.left < viewport.innerWidth;
    }
    function render(count) {
      if (!badge || !label) return;
      if (!Number.isSafeInteger(count) || count < 0) { reset(); return; }
      const text = `${count.toLocaleString()} watching live`;
      if (label.textContent !== text) label.textContent = text;
      receivedAt = clock();
      badge.hidden = false;
    }
    const timer = viewport.setInterval(() => {
      // A disconnected browser must not keep presenting an old number as live.
      if (receivedAt !== null && clock() - receivedAt >= 30000) reset();
    }, 1000);
    viewport.addEventListener('pagehide', reset);
    return {watching, render, reset,
      close() { viewport.clearInterval(timer); viewport.removeEventListener('pagehide', reset); reset(); }};
  }
  window.yamLiveViewers = {create};
})();
