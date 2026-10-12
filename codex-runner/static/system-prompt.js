/* Per-robot, per-model prompt drafts; never modify an active conversation. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const field = $('systemPromptText'), menu = $('systemPromptPreset'), box = $('systemPromptSettings');
  if (!field || !menu || !box) return;
  let data = {}, robot = '', identity = '', draft = null;
  const presets = () => data.presets || [];
  const defaultId = () => /^claude-opus-/.test($('model').value.trim()) ? 'roboharm-cartesian' : 'with-haste';
  const supported = () => data.enabled && ['openai','codex','anthropic','claude','guest_astra','guest_claude'].includes($('provider').value)
    && !(!$('apiDepthSettings').hidden && $('useApiDepth').checked);
  const key = () => 'blupe-system-prompt:' + robot + ':' + $('provider').value + ':' + $('model').value.trim();
  function render() {
    const preset = presets().find(p => p.id === draft?.preset);
    const custom = draft?.custom === true;
    menu.value = custom ? 'custom' : preset?.id || '';
    field.value = draft?.text || '';
    field.setCustomValidity('');
    $('systemPromptName').textContent = custom ? '· Custom' : preset ? '· ' + preset.label : '';
    $('systemPromptNote').textContent = custom ? 'Your edits replace the behavioral prompt. The final prompt is recorded in the run conversation.' : preset?.note || '';
    const source = $('systemPromptSource'); source.hidden = !preset?.source_url;
    if (preset?.source_url) source.href = preset.source_url;
  }
  function save() {
    try { localStorage.setItem(identity, JSON.stringify(draft)); } catch (_) {}
  }
  function sync(force = false) {
    const visible = !!supported();
    if (box.hidden === visible) box.hidden = !visible;
    if (field.disabled === visible) field.disabled = !visible;
    if (menu.disabled === visible) menu.disabled = !visible;
    if (!visible) return;
    const next = key();
    if (!force && next === identity) return;
    identity = next; draft = null;
    try { draft = JSON.parse(localStorage.getItem(identity)); } catch (_) {}
    if (!draft || typeof draft.text !== 'string' || !presets().some(p => p.id === draft.preset)) {
      const preset = presets().find(p => p.id === defaultId()) || presets()[0];
      if (!preset) {box.hidden = true; return;}
      draft = {preset:preset.id, text:preset.text, custom:false};
    }
    menu.replaceChildren(...presets().map(p => new Option(p.label, p.id)), new Option('Custom', 'custom'));
    render();
  }
  menu.addEventListener('change', () => {
    const preset = presets().find(p => p.id === menu.value);
    if (preset) draft = {preset:preset.id, text:preset.text, custom:false};
    else if (draft) draft.custom = true;
    save(); render();
  });
  field.addEventListener('input', () => {
    if (!draft) return;
    draft.text = field.value; draft.custom = true; save();
    menu.value = 'custom'; $('systemPromptName').textContent = '· Custom';
    field.setCustomValidity(new TextEncoder().encode(field.value).length > (data.max_bytes || 16000)
      ? 'Use at most 16,000 UTF-8 bytes.' : !field.value.trim() ? 'Enter a system prompt.' : '');
  });
  $('resetSystemPrompt').addEventListener('click', () => {
    const preset = presets().find(p => p.id === defaultId());
    if (!preset) return;
    draft = {preset:preset.id, text:preset.text, custom:false};
    field.setCustomValidity(''); save(); render();
  });
  document.addEventListener('blupe-model-changed', () => sync());
  $('provider').addEventListener('change', () => sync());
  $('useApiDepth').addEventListener('change', () => sync());
  window.yamSystemPrompt = {
    configure(value, id) {data = value || {}; robot = id || ''; identity = ''; sync(true);}, sync,
    payload() {
      sync(); if (!supported() || !draft) return {};
      return draft.custom ? {system_prompt:draft.text} : {system_prompt_preset:draft.preset};
    }
  };
})();
