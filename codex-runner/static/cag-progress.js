/* Pure status projection shared with the comparison UI tests. */
(function (root) {
  'use strict';
  function cagProgress(state, enabled = true) {
    if (!enabled) return {phase:'unavailable', text:'GPU service is unavailable. Cameras and previous runs remain available.'};
    const provider = state.provider || {};
    if (state.status === 'preparing' && !state.session_id && provider.warmup !== 'failed') {
      const seconds = Math.max(0, Math.floor(Number(provider.warmup_elapsed_s) || 0));
      const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
      return {phase:'starting', text:`Starting GPU · loading MolmoAct2 on RunPod · ${elapsed} elapsed. This can take a few minutes. The robot will join the queue when the model is ready. You can cancel with Stop.`};
    }
    if (state.status === 'failed' || provider.warmup === 'failed') return {phase:'failed', text:state.error || 'GPU startup failed. The robot has not started this task.'};
    if (state.status === 'queued') return {phase:'queued', text:'GPU ready · waiting for your turn in the robot queue.'};
    if (state.status === 'preparing') return {phase:'preparing', text:'GPU ready · preparing the robot for your task.'};
    if (state.status === 'running' && Number(state.run_elapsed_s)>=Number(state.run_duration_s) && Number(state.run_duration_s)>0) return {phase:'finishing',text:'Time limit reached · waiting for the robot to confirm it has stopped. Stop remains available.'};
    if (state.status === 'running') return {phase:'running', text:`GPU ready · ${state.runner_name || 'Your run'} · MolmoAct2 is running your task. Follow the live cameras above.`};
    if (['timed_out','stopped','completed'].includes(state.status)) return {phase:'finished',text:`${state.runner_name || 'Your run'} · Run finished. Check Your runs below for the recording; it may take a moment to prepare.`};
    return {phase:'available', text:'RunPod GPU available on demand. Press Run to start MolmoAct2. GPU startup progress will appear here; cameras remain live while you wait.'};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = cagProgress;
  else root.cagProgress = cagProgress;
})(typeof window === 'undefined' ? globalThis : window);
