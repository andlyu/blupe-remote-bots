/* Independent public annotations; never replace human assessments or votes. */
(() => {
  'use strict';
  const labels = new Set(['Success', 'Failure', 'Uncertain']);
  let records = new Map(), pending = null, loaded = false, unavailable = false, replaySequence = 0;
  const key = run => `${run.robot_id || ''}:${run.episode_id}`;
  const record = run => records.get(key(run)) || {};
  async function load() {
    if (loaded) return;
    if (!pending) pending = (async () => {
      try {
        const response = await fetch('/api/run-labels', {cache:'no-store'});
        if (!response.ok) throw new Error('Labels unavailable');
        const data = await response.json();
        if (data.version !== 1 || !Array.isArray(data.runs) || data.runs.some(run =>
          !run.episode_id || !run.robot_id || !labels.has(run.auto_assessment?.label) ||
          (run.human_review && !labels.has(run.human_review.label)))) throw new Error('Invalid labels');
        records = new Map(data.runs.map(run => [key(run), run]));
        loaded = true; unavailable = false;
      } catch (_) { unavailable = true; }
      finally { pending = null; }
    })();
    return pending;
  }
  function outcome(run, source = 'human') {
    const saved = record(run), a = run.assessment || {};
    if (source === 'auto') return saved.auto_assessment?.label || 'Unscored';
    if (a.label) return a.eligibility === 'included' && labels.has(a.label) ? a.label : 'Unscored';
    if (a.ended === false) return 'Unscored';
    return saved.human_review?.label || (labels.has(a.community?.label) ? a.community.label : 'Unscored');
  }
  function describe(run, source) {
    const saved = record(run), a = run.assessment || {}, result = outcome(run, source);
    if (source === 'auto') return saved.auto_assessment
      ? `Auto-labeled: ${result} · ${saved.auto_assessment.model} · ${saved.auto_assessment.reason}`
      : 'Auto-labeled: Not labeled yet';
    const provenance = a.label ? 'Runner' : saved.human_review ? 'Human trial review' : 'Community';
    return `Human-labeled: ${result === 'Unscored' ? 'Unlabeled or excluded' : result} · ${provenance}`;
  }
  function summary(runs, source) {
    if (unavailable) return 'Auto-labels and imported trial reviews are unavailable. Select Refresh to retry. Runner labels and community votes remain available.';
    if (!loaded) return 'Loading label sources…';
    const counts = {Success:0, Failure:0, Uncertain:0, Unscored:0};
    for (const run of runs) counts[outcome(run, source)]++;
    const count = runs.length - counts.Unscored;
    return `${source === 'auto' ? 'Auto-labeled' : 'Human-labeled'}: ${count} of ${runs.length} shown · ${counts.Success} Success · ${counts.Failure} Failure · ${counts.Uncertain} Uncertain · ${counts.Unscored} unlabeled or excluded.${source === 'auto' ? ' Gemini 3.8 Flash predictions; review before relying on them.' : ' Runner assessments, human trial reviews and community votes.'}`;
  }
  async function showReplay(run, anchor) {
    const sequence = ++replaySequence;
    document.getElementById('runLabelEvidence')?.remove();
    await load();
    if (sequence !== replaySequence) return;
    const saved = record(run), panel = document.createElement('details');
    panel.id = 'runLabelEvidence'; panel.className = 'runLabelEvidence';
    const title = document.createElement('summary'), prediction = saved.auto_assessment;
    title.textContent = prediction ? `Auto-labeled: ${prediction.label} · ${prediction.model}` : 'Auto-labeled: Not labeled yet';
    panel.append(title);
    function paragraph(text) { const p = document.createElement('p'); p.textContent = text; panel.append(p); }
    if (prediction) {
      paragraph(prediction.reason);
      paragraph(`Model confidence: ${prediction.confidence}. Rubric: ${prediction.rubric_version}.`);
      for (const item of prediction.evidence || []) paragraph(`${item.timestamp_s}s in reviewed video: ${item.observation}`);
      for (const limitation of prediction.limitations || []) paragraph(`Limitation: ${limitation}`);
      paragraph('Prediction is separate from the human assessment. For “pick up,” a clear lift with control counts even if later released.');
    }
    if (saved.human_review) paragraph(`Human trial review: ${saved.human_review.label} · ${new Date(saved.human_review.reviewed_at).toLocaleString()}`);
    anchor.after(panel);
  }
  window.yamRunLabels = {load, outcome, describe, summary, showReplay};
})();
