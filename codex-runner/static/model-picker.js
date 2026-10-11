/* Provider catalogs are suggestions; every run retains its explicit model ID. */
(function(root) {
  'use strict';
  function createModelPicker({$, api, storage, changed = () => {}, context = () => ''}) {
    const defaults = {openai:'gpt-6-astra', codex:'gpt-6-astra', anthropic:'claude-opus-5-5', claude:'claude-opus-5-5', guest_astra:'gpt-6-astra', guest_claude:'claude-opus-5-5'};
    const selected = new Map(), catalogs = new Map();
    let provider = null, fixed = false, lockedModel = false, generation = 0, loading = false, effortIdentity = null;
    const key = name => 'blupe-model:' + name;
    const effortKey = () => 'blupe-effort:' + provider + ':' + $('model').value.trim();
    const labels = {none:'None',minimal:'Minimal',low:'Low',medium:'Medium',high:'High',xhigh:'Extra High',max:'Max',ultra:'Ultra'};
    let efforts = [], defaultEffort = 'low';
    const nodeOption = (value, label) => {
      const option = $('model').ownerDocument.createElement('option');
      option.value = value; option.textContent = label; return option;
    };
    function saveSelection() {
      if (!provider || fixed) return;
      const value = $('model').value.trim();
      selected.set(provider, value);
      try { storage?.setItem(key(provider), value); } catch (_) {}
    }
    function saveEffort() {
      if (!effortIdentity || !efforts.includes($('reasoningEffort').value)) return;
      try { storage?.setItem(effortIdentity, $('reasoningEffort').value); } catch (_) {}
    }
    function renderEffort() {
      const field = $('reasoningEffort'), slider = $('reasoningLevel');
      if (!slider || !efforts.length) return;
      const index = Math.max(0, efforts.indexOf(field.value));
      slider.min = '0'; slider.max = String(efforts.length - 1); slider.step = '1'; slider.value = String(index);
      slider.disabled = field.disabled || efforts.length < 2;
      slider.setAttribute?.('aria-valuetext', labels[field.value] || field.value);
      slider.style?.setProperty('--reasoning-fill', (efforts.length < 2 ? 100 : 100 * index / (efforts.length - 1)) + '%');
      $('reasoningLabel').textContent = labels[field.value] || field.value;
      const entry = catalogs.get(provider)?.models.find(model => model.id === $('model').value.trim());
      $('reasoningModel').textContent = entry?.label || $('model').value.trim();
      $('reasoningTicks').replaceChildren(...efforts.map((effort, i) => nodeOption(String(i), labels[effort] || effort)));
      $('reasoningBar').hidden = false; field.hidden = true;
    }
    function applyEffort() {
      if (!['codex', 'claude', 'guest_astra', 'guest_claude'].includes(provider) || fixed) return;
      const entry = catalogs.get(provider)?.models.find(model => model.id === $('model').value.trim());
      const fallback = ['codex','guest_astra'].includes(provider) ? ['low','medium','high','xhigh','max','ultra'] : ['low','medium','high','xhigh','max'];
      efforts = entry?.reasoning_efforts?.length ? entry.reasoning_efforts.filter(effort => labels[effort]) : fallback;
      if (!efforts.length) efforts = fallback;
      const field = $('reasoningEffort'), previous = field.value;
      const identity = effortKey();
      let saved; try { saved = storage?.getItem(identity); } catch (_) {}
      defaultEffort = entry?.default_reasoning_effort || (['claude','guest_claude'].includes(provider) ? 'medium' : provider === 'guest_astra' ? 'high' : efforts[0]);
      if (!efforts.includes(defaultEffort)) defaultEffort = efforts[0];
      field.replaceChildren(...efforts.map(effort => nodeOption(effort, labels[effort])));
      field.value = efforts.includes(saved) ? saved : effortIdentity === identity && efforts.includes(previous) ? previous : provider.startsWith('guest_') && efforts.includes('high') ? 'high' : defaultEffort;
      effortIdentity = identity;
      renderEffort();
    }
    function renderCatalog() {
      const catalog = catalogs.get(provider);
      $('availableModels').replaceChildren(...(catalog?.models || []).map(model => nodeOption(model.id, model.label)));
      $('modelCatalogStatus').textContent = catalog?.message || 'Choose Astra or GPT 6.1+, or Claude Opus 5.5+. Enter a model ID or refresh the list.';
      applyEffort();
    }
    async function refresh(force = false) {
      if (fixed || !defaults[provider] || loading && !force || $('model').disabled) return;
      const previous = catalogs.get(provider);
      if (!force && previous && Date.now() - previous.fetched < 300000) return;
      const requestProvider = provider, requestContext = context(), requestGeneration = ++generation;
      loading = true; $('refreshModels').disabled = true;
      $('modelCatalogStatus').textContent = 'Loading models…';
      try {
        const result = await api('/api/models', {provider: requestProvider,
          ...(['openai','anthropic'].includes(requestProvider) ? {api_key:$('apiKey').value.trim()} : {})});
        if (requestGeneration !== generation || requestProvider !== provider || requestContext !== context()) return;
        if (!Array.isArray(result.models)) throw new Error('Invalid model catalog');
        // A failed refresh must not discard a previously fetched catalog.
        const models = result.source === 'fallback' && previous ? previous.models : result.models;
        catalogs.set(provider, {...result, models, fetched:Date.now()});
        renderCatalog();
      } catch (error) {
        if (requestGeneration === generation && requestContext === context() && !error.stale)
          $('modelCatalogStatus').textContent = 'Could not refresh models. Your selection is unchanged; you can enter a model ID directly.';
      } finally {
        if (requestGeneration === generation) { loading = false; $('refreshModels').disabled = $('model').disabled; }
      }
    }
    function providerChanged({fixed: isFixed = false, fixedModel = false} = {}) {
      const next = $('provider').value;
      const changedProvider = next !== provider || fixed !== isFixed;
      provider = next; fixed = isFixed || !defaults[next]; lockedModel = fixedModel;
      if (changedProvider) { generation++; loading = false; }
      $('modelSettings').hidden = fixed || lockedModel;
      $('model').required = !fixed;
      if (fixed) return;
      let saved = selected.get(provider);
      if (saved === undefined) { try { saved = storage?.getItem(key(provider)); } catch (_) {} }
      $('model').value = lockedModel ? defaults[provider] : saved || defaults[provider];
      $('refreshModels').disabled = $('model').disabled;
      renderCatalog();
      changed();
      void refresh();
    }
    function reset() {
      generation++; loading = false; catalogs.clear();
    }
    $('model').addEventListener('input', () => { saveEffort(); saveSelection(); applyEffort(); changed(); });
    $('reasoningEffort').addEventListener('change', () => { saveEffort(); renderEffort(); });
    $('reasoningLevel')?.addEventListener('input', () => {
      const value = efforts[Number($('reasoningLevel').value)];
      if (value) { $('reasoningEffort').value = value; saveEffort(); renderEffort(); }
    });
    $('resetReasoning')?.addEventListener('click', () => { $('reasoningEffort').value = defaultEffort; saveEffort(); renderEffort(); });
    $('refreshModels').addEventListener('click', () => { void refresh(true); });
    $('apiKey').addEventListener('change', () => { void refresh(true); });
    return {saveSelection:() => { saveEffort(); saveSelection(); }, providerChanged, refresh, reset};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {createModelPicker};
  else root.createBlupeModelPicker = createModelPicker;
})(typeof window === 'undefined' ? globalThis : window);
