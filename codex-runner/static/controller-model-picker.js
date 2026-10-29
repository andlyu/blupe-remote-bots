/* Execution routing is independent from the existing runner's model picker. */
(function(root) {
  function controllerDreamChoices(models, hosted) {
    const direct = {};
    for (const row of Object.values(models || {})) {
      if (row.available && !row.custom && ['dream','dream_flash'].includes(row.provider))
        direct[row.provider] = {model:row.model,label:row.label};
    }
    return {...direct, ...(hosted || {})};
  }
  function automaticControllerModel(models, provider, model) {
    const family = name => ({codex:'openai',guest_astra:'openai',
      claude:'anthropic',guest_claude:'anthropic',guest_gemini:'gemini'}[name] || name);
    return Object.entries(models || {}).find(([, row]) => row.available &&
      !row.custom && !row.user_endpoint && row.model === model.trim() &&
      family(row.provider) === family(provider));
  }
  function controllerPayload(spec, id, endpoint, model) {
    if (!spec || !spec.available) throw new Error(spec?.reason || 'Controller model is unavailable on this robot.');
    const payload = {executor:'controller', controller_model:id, provider:spec.provider,
      model:spec.user_endpoint ? model.trim() : spec.model, api_key:'', use_api_depth:false};
    if (spec.user_endpoint) {
      const url = new URL(endpoint);
      if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash)
        throw new Error('Enter a public HTTPS inference endpoint without credentials or query parameters.');
      if (!payload.model) throw new Error('Enter the model ID expected by your endpoint.');
      payload.custom_endpoint = {protocol:'responses_v1',url:url.href};
    }
    return payload;
  }
  function createControllerModelPicker($, changed) {
    let models = {}, signature = null;
    const manual = () => $('executionLocation').value === 'controller';
    const automatic = () => automaticControllerModel(models, $('provider').value, $('model').value);
    const choice = () => manual() ? [$('controllerModel').value, models[$('controllerModel').value]]
      : $('executionLocation').value === 'auto' ? automatic() : null;
    const selected = () => manual() || !!choice();
    function sync() {
      const controller = selected(), item = choice()?.[1];
      $('controllerModelSettings').hidden = !manual();
      $('controllerEndpointSettings').hidden = !controller || !item?.user_endpoint;
      $('controllerEndpoint').required = $('controllerEndpointModel').required = controller && !!item?.user_endpoint;
      $('executionLocation').querySelector('[value="auto"]').textContent = automatic()
        ? 'Automatic · robot controller' : 'Automatic · BLUPE runner';
      $('controllerExecutionHelp').textContent = controller
        ? item?.available ? item.label + ' runs on this robot’s controller and calls the model directly.' : item?.reason || 'Choose an available controller model.'
        : 'The existing BLUPE runner collects observations and calls the selected model.';
      // Automatic mode keeps the ordinary model picker usable.
      $('provider').disabled ||= manual();
      $('model').disabled ||= manual();
      $('apiKey').disabled ||= controller;
      if (controller) $('apiKey').required = false;
    }
    $('executionLocation').addEventListener('change', () => {
      if (manual() && automatic()) $('controllerModel').value = automatic()[0];
      changed(); sync();
    });
    $('controllerModel').addEventListener('change', () => { changed(); sync(); });
    return {selected, sync,
      label:() => choice()?.[1]?.label || 'Controller model',
      configure(rows) {
        const next = JSON.stringify(rows || {});
        if (signature === next) { sync(); return; }
        signature = next;
        const previous = $('controllerModel').value;
        models = rows || {};
        if (!['auto','runner','controller'].includes($('executionLocation').value)) $('executionLocation').value = 'auto';
        $('executionLocation').querySelector('[value="controller"]').disabled = !Object.values(models).some(row => row.available);
        $('controllerModel').replaceChildren(...Object.entries(models).map(([id, row]) =>
          Object.assign($('controllerModel').ownerDocument.createElement('option'), {value:id, textContent:row.label + (row.available ? '' : ' — unavailable'), disabled:!row.available})));
        $('controllerModel').value = previous && models[previous] ? previous
          : manual() && previous ? '' : automatic()?.[0] || Object.keys(models).find(id => models[id].available) || '';
        sync();
      },
      payload() {
        const row = choice();
        return selected() ? controllerPayload(row?.[1], row?.[0],
          $('controllerEndpoint').value, $('controllerEndpointModel').value) : {};
      }
    };
  }
  root.createControllerModelPicker = createControllerModelPicker;
  root.controllerDreamChoices = controllerDreamChoices;
  if (typeof module !== 'undefined') module.exports = {controllerPayload, automaticControllerModel, createControllerModelPicker, controllerDreamChoices};
})(typeof window !== 'undefined' ? window : globalThis);
