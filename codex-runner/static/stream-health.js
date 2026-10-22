/* Frame callbacks and their timing fields: docs/refs/canvas/requestVideoFrameCallback.html. */
(() => {
  'use strict';
  class StreamHealth {
    constructor(video, {badge, detail, recover, report, clock = () => performance.now()}) {
      Object.assign(this, {video, badge, detail, recover, report, clock});
      this.started = clock(); this.lastFrame = null; this.frameTimes = [];
      this.delay = null; this.previous = null; this.lastRecovery = -Infinity;
      this.closed = false; this.frameId = null;
      const presented = (now, metadata) => {
        if (this.closed) return;
        if (!document.hidden && video.readyState >= 2 && !video.paused) {
          this.presented(metadata.captureTime);
        }
        this.frameId = video.requestVideoFrameCallback(presented);
      };
      if (video.requestVideoFrameCallback) this.frameId = video.requestVideoFrameCallback(presented);
      else video.addEventListener('timeupdate', () => {
        if (!this.closed && !document.hidden && !video.paused && video.readyState >= 2 && video.currentTime !== this.lastMediaTime) {
          this.lastMediaTime = video.currentTime; this.lastFrame = this.clock();
        }
      });
      this.interval = setInterval(() => this.tick(), 250);
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden) { this.started = this.clock(); this.lastFrame = null; this.frameTimes = []; }
        this.tick();
      });
      window.addEventListener('pagehide', () => this.close());
      this.tick();
    }
    presented(captureTime, fromCanvas = false) {
      if (this.closed || document.hidden || this.video.paused || this.video.readyState < 2) return;
      const quality = this.video.getVideoPlaybackQuality?.();
      const decoded = quality ? quality.totalVideoFrames - quality.droppedVideoFrames : null;
      // Canvas rendering can continue while an occluded 1px source receives no
      // frame callbacks. Require new decoded video, not an advancing audio clock.
      if (fromCanvas && (!Number.isFinite(decoded) || decoded <= 0)) return;
      const now = this.clock();
      if (Number.isFinite(captureTime) && now >= captureTime) this.delay = now - captureTime;
      if (decoded !== null && decoded === this.lastDecoded) return;
      this.lastDecoded = decoded;
      this.lastFrame = now;
      this.frameTimes.push(now);
      this.frameTimes = this.frameTimes.filter(t => now - t <= 5000);
      if (!Number.isFinite(captureTime)) this.delay = null;
    }
    snapshot() {
      const now = this.clock(), age = this.lastFrame === null ? null : now - this.lastFrame;
      const transport = this.video.dataset.transport || 'unknown';
      // The last presented image keeps aging even when no new frame arrives.
      let delay = this.delay === null ? null : this.delay + (age || 0);
      if (transport === 'hls') {
        delay = null;
        if (this.video.seekable.length) delay = Math.max(0, (this.video.seekable.end(this.video.seekable.length - 1) - this.video.currentTime) * 1000);
      }
      for (const estimate of [this.video.yamPlaybackDelay?.(), this.video.yamCaptureAge?.()]) {
        if (Number.isFinite(estimate) && estimate >= 0) delay = Math.max(delay || 0, estimate);
      }
      const recent = this.frameTimes.filter(t => now - t <= 5000);
      const span = recent.length > 1 ? recent[recent.length - 1] - recent[0] : 0;
      const fps = span > 0 ? (recent.length - 1) * 1000 / span : 0;
      let state = 'connecting';
      if (document.hidden) state = 'paused';
      else if (age !== null && age > 2000) state = 'stalled';
      else if (delay !== null && delay > 2000) state = 'behind';
      else if (age === null) state = now - this.started >= 8000 ? 'stalled' : 'connecting';
      else state = transport === 'hls' ? 'delayed' : 'live';
      return {state, transport, frame_age_ms: age === null ? null : Math.round(age),
        delay_ms: delay === null ? null : Math.round(delay), fps: Math.round(fps * 10) / 10};
    }
    tick() {
      if (this.closed) return;
      const data = this.snapshot();
      const quality = this.video.getVideoPlaybackQuality?.();
      if (quality) {
        this.video.dataset.decodedFrames = String(quality.totalVideoFrames);
        this.video.dataset.droppedFrames = String(quality.droppedVideoFrames);
      }
      const names = {connecting:'Checking stream', live:'Live video', delayed:'Video playing · delayed',
        behind:'Video over 2s old · catching up', stalled:'Stream stalled · reconnecting', paused:'Stream paused in background'};
      if (this.badge) {
        this.badge.textContent = names[data.state]; this.badge.dataset.state = data.state;
        this.badge.title = 'Checks frames presented in this browser. Delay is estimated when available.';
      }
      if (this.detail) this.detail.textContent = ['live','delayed','behind'].includes(data.state)
        ? `${data.fps ? data.fps + ' fps' : 'Frames advancing'}${data.delay_ms !== null ? ' · ' + (data.delay_ms / 1000).toFixed(1) + 's estimated delay' : ''}` : '';
      if (data.state !== this.previous) {
        console.info('[stream-health]', data);
        this.report?.(data); this.previous = data.state;
      }
      const outage = this.lastFrame === null ? this.clock() - this.started : this.clock() - this.lastFrame;
      if (!document.hidden && this.clock() - this.lastRecovery >= 2000 &&
          ((data.state === 'stalled' && outage >= 8000) ||
           data.state === 'behind')) {
        this.lastRecovery = this.clock(); this.recover(data);
      }
    }
    stale() { return this.snapshot().state === 'stalled'; }
    reset() {
      this.started = this.clock(); this.lastFrame = null; this.frameTimes = [];
      this.delay = null; this.lastDecoded = null;
    }
    close() {
      this.closed = true; clearInterval(this.interval);
      if (this.frameId !== null) this.video.cancelVideoFrameCallback?.(this.frameId);
    }
  }
  window.YamStreamHealth = StreamHealth;
})();
