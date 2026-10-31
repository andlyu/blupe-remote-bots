/* Pure startup projection; native progress is not visual motion verification. */
(function (root) {
  'use strict';
  const number = v => typeof v === 'number' && Number.isFinite(v) && v > 0;
  const clock = v => new Date(v * 1000).toISOString().slice(11, 23) + ' UTC';
  const duration = v => `${Math.max(0, v).toFixed(1)}s`;
  function cagProgress(state, enabled = true, now = Date.now() / 1000) {
    const provider = state.provider || state.run_configuration || {};
    const startup = state.cag_startup || {};
    const gpu = startup.gpu || provider.gpu_startup || {};
    const home = startup.home || provider.startup_home;
    const queue = startup.queue || provider.startup_queue || {};
    const stages = [];
    if (number(gpu.launch_started_at)) {
      stages.push(`GPU launch started ${clock(gpu.launch_started_at)}`);
      if (number(gpu.ready_at)) stages.push(`GPU + MolmoAct2 ready ${clock(gpu.ready_at)} · startup ${duration(gpu.ready_at - gpu.launch_started_at)}`);
    } else if (number(gpu.ready_at)) {
      stages.push(`${gpu.launch_required === false ? 'Existing GPU' : 'GPU + MolmoAct2'} ready ${clock(gpu.ready_at)}`);
    }
    if (number(queue.entered_at)) stages.push(`Robot queue entered ${clock(queue.entered_at)}`);
    if (number(queue.admitted_at)) stages.push(`Robot admission confirmed ${clock(queue.admitted_at)}`);
    if (number(home?.completed_at)) stages.push(`Both arms settled at Home ${clock(home.completed_at)}`);
    const result = (phase, text) => ({phase, text, stages});
    if (!enabled) return result('unavailable', 'GPU service is unavailable. Cameras and previous runs remain available.');
    if (state.status === 'failed' || provider.warmup === 'failed') return result('failed', state.error || 'Startup failed. Use Stop before trying another run.');
    if (state.status === 'preparing' && !state.session_id) {
      if (gpu.launch_required === true && number(gpu.launch_started_at)) {
        return result('starting', `Starting GPU · loading MolmoAct2 on RunPod · ${duration(now - gpu.launch_started_at)} elapsed. The robot will join the queue when the model is ready. You can cancel with Stop.`);
      }
      return result('checking', `${gpu.launch_required === false ? 'GPU already available · checking MolmoAct2 readiness' : 'Checking RunPod GPU availability'}. The robot joins the queue after readiness is confirmed. You can cancel with Stop.`);
    }
    if (state.status === 'queued') return result('queued', 'GPU ready · waiting for robot admission. The arms may move Home during normal queue preparation.');
    if (state.status === 'preparing') return result('preparing', 'GPU ready · preparing both arms and moving Home. Method execution has not started.');
    if (state.status === 'running' && Number(state.run_elapsed_s) >= Number(state.run_duration_s) && Number(state.run_duration_s) > 0) return result('finishing', 'Time limit reached · waiting for the robot to confirm it has stopped. Stop remains available.');
    if (state.status === 'running') {
      const confirmed = Number(state.run_metrics?.confirmed_waypoints || 0);
      if (confirmed === 0) {
        const elapsed = number(home?.completed_at) ? ` · ${duration(now - home.completed_at)} since Home` : '';
        const late = number(home?.completed_at) && now - home.completed_at > 15;
        return result('first_action', `${home ? 'Home confirmed' : 'Robot admitted'} · preparing the first MolmoAct2 action${elapsed}.${late ? ' First action is taking longer than the 15s target.' : ''} Follow the live cameras for physical motion. Stop remains available.`);
      }
      return result('running', `GPU ready · ${state.runner_name || 'Your run'} · robot reports MolmoAct2 action progress. Follow the live cameras above.`);
    }
    if (['timed_out', 'stopped', 'completed'].includes(state.status)) return result('finished', `${state.runner_name || 'Your run'} · Run finished. Check Your runs below for the recording; it may take a moment to prepare.`);
    return result('available', 'RunPod GPU available on demand. Press Run to start MolmoAct2. GPU startup progress will appear here; cameras remain live while you wait.');
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = cagProgress;
  else root.cagProgress = cagProgress;
})(typeof window === 'undefined' ? globalThis : window);
