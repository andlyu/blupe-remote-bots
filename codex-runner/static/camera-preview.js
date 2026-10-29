/* A read-only still fills the initial canvases while session/live video connect. */
(() => {
  'use strict';
  let robot = '', image = null, generation = 0, requestedAt = 0;
  const selected = () => document.getElementById('robotSelector')?.value;
  function paint(targetRobot, tiles) {
    if (targetRobot !== robot || !image || performance.now() - requestedAt > 5000) return;
    const width = image.naturalWidth, height = image.naturalHeight;
    const hd = width * 27 === height * 64;
    let painted = false;
    tiles.forEach((tile, i) => {
      if (tile.dataset.frameSource === 'video' || tile.dataset.frameSource === 'snapshot') return;
      const role = tile.dataset.cameraRole;
      const rect = hd ? ({observer:[0,0,width*3/4,height],left:[width*3/4,0,width/4,height/3],top:[width*3/4,height/3,width/4,height/3],right:[width*3/4,height*2/3,width/4,height/3]})[role]
        : [(i%2)*width/2, Math.floor(i/2)*height/2, width/2, height/2];
      if (!rect) return;
      tile.width = rect[2]; tile.height = rect[3];
      tile.getContext('2d', {alpha:false}).drawImage(image, ...rect, 0, 0, rect[2], rect[3]);
      tile.dataset.frameSource = 'preview';
      const label = tile.closest('figure')?.querySelector('[data-sync-status]');
      if (label) label.textContent = 'Still image · Connecting';
      painted = true;
    });
    if (painted) {
      const viewer = document.getElementById('liveViewer');
      if (viewer && !viewer.dataset.firstCameraMs) {
        requestAnimationFrame(() => { viewer.dataset.firstCameraMs ||= performance.now().toFixed(1); });
      }
    }
  }
  window.yamCameraPreview = {paint};
  async function load(targetRobot) {
    const current = ++generation;
    robot = targetRobot; image = null; requestedAt = performance.now();
    // These paths already carry public video. Unsupported robots use normal startup.
    if (!['yam-1','robot-ba8413962083809c'].includes(robot)) return;
    const snapshot = new Image();
    snapshot.fetchPriority = 'high';
    snapshot.onload = async () => {
      try {
        await snapshot.decode();
        if (current !== generation || document.hidden) return;
        if (![[2560,1080],[1280,540],[1280,720],[1024,432],[1024,576]].some(([w,h]) => snapshot.naturalWidth === w && snapshot.naturalHeight === h)) return;
        image = snapshot;
        const tiles = [...document.querySelectorAll('[data-sync-tile]')];
        const roles = robot === 'yam-1' ? ['top','observer','left','right'] : ['top','left','right','observer'];
        tiles.forEach((tile,i) => {
          if (tile.dataset.cameraRole) return;
          const role = roles[i], figure = tile.closest('figure');
          tile.dataset.cameraRole = role;
          tile.setAttribute('aria-label', role + ' robot camera');
          if (figure) {
            figure.dataset.cameraRole = role;
            const caption = figure.querySelector('figcaption');
            if (caption?.firstChild) caption.firstChild.textContent = role[0].toUpperCase() + role.slice(1) + ' ';
            figure.querySelector('[data-expand-camera]')?.setAttribute('aria-label', 'Expand ' + role + ' camera');
          }
        });
        const viewer = document.getElementById('liveViewer');
        if (viewer) viewer.dataset.layout = 'observer-focus';
        paint(robot, tiles);
      } catch { /* The existing JPEG/live startup remains the fallback. */ }
    };
    snapshot.src = '/synchronized/preview.jpg?robot_id=' + encodeURIComponent(robot);
  }
  window.addEventListener('blupe-robot-selected', event => {
    if (event.detail !== robot) load(event.detail);
  });
  function start() {
    // The selector resolves catalog order, explicit links and dedicated pages.
    // Read it here too in case this async script missed the selection event.
    const resolved = selected();
    if (resolved && resolved !== robot) load(resolved);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
