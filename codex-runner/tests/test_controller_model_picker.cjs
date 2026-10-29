const assert = require('node:assert/strict');
const {controllerPayload} = require('../static/controller-model-picker.js');
const fixed = {provider:'dream_flash',model:'dreamlabs/dream-1-beta-flash',available:true};
assert.deepEqual(controllerPayload(fixed,'dream_flash','',''), {executor:'controller',controller_model:'dream_flash',provider:fixed.provider,model:fixed.model,api_key:'',use_api_depth:false});
const custom = {provider:'custom',user_endpoint:true,available:true};
assert.equal(controllerPayload(custom,'custom','https://example.com/v1/responses','my-model').custom_endpoint.protocol,'responses_v1');
for (const url of ['http://example.com','https://user:password@example.com','https://example.com?key=private'])
  assert.throws(()=>controllerPayload(custom,'custom',url,'my-model'));
assert.throws(()=>controllerPayload({...fixed,available:false},'dream_flash','',''));
console.log('Controller model selection preserves registered checkpoints and validates user endpoints.');
