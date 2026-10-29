/* Execution routing is independent from the existing runner's model picker. */
(function(root) {
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
    let models = {};
    const selected = () => $('executionLocation').value === 'controller';
    const spec = () => models[$('controllerModel').value];
    function sync() {
      const controller = selected(), item = spec();
      $('controllerModelSettings').hidden = !controller;
      $('controllerEndpointSettings').hidden = !controller || !item?.user_endpoint;
      $('controllerEndpoint').required = $('controllerEndpointModel').required = controller && !!item?.user_endpoint;
      $('controllerExecutionHelp').textContent = controller
        ? item?.available ? 'The adapter runs on this robot’s controller and calls the model directly.' : item?.reason || 'No controller model is installed.'
        : 'The existing BLUPE runner collects observations and calls the model.';
      $('provider').disabled ||= controller;
      $('model').disabled ||= controller;
      $('apiKey').disabled ||= controller;
      if (controller) $('apiKey').required = false;
    }
    $('executionLocation').addEventListener('change', () => { changed(); sync(); });
    $('controllerModel').addEventListener('change', sync);
    return {selected, sync,
      label:() => spec()?.label || 'Controller model',
      configure(rows) {
        models = rows || {};
        $('executionLocation').value = 'runner';
        $('executionLocation').querySelector('[value="controller"]').disabled = !Object.keys(models).length;
        $('controllerModel').replaceChildren(...Object.entries(models).map(([id, row]) =>
          Object.assign(document.createElement('option'), {value:id, textContent:row.label + (row.available ? '' : ' — unavailable'), disabled:!row.available})));
        $('controllerEndpoint').value = ''; $('controllerEndpointModel').value = '';
        sync();
      },
      payload() { return selected() ? controllerPayload(spec(), $('controllerModel').value,
        $('controllerEndpoint').value, $('controllerEndpointModel').value) : {}; }
    };
  }
  root.createControllerModelPicker = createControllerModelPicker;
  if (typeof module !== 'undefined') module.exports = {controllerPayload};
})(typeof window !== 'undefined' ? window : globalThis);
