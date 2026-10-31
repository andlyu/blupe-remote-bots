const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../static/hosted.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
const begin=js.indexOf('  let attentionSession =');const end=js.indexOf('  function renderAstraStream(',begin);
for(const [,id] of js.slice(begin,end).matchAll(/\$\('([^']+)'\)/g))assert.ok(html.includes('id="'+id+'"') || id === 'runExecutionInfo' && js.includes("card.id = 'runExecutionInfo'"),id+' missing from deployed HTML or dynamic construction');

// Run controls must also target real markup after optional policies are removed.
const buttons=js.slice(js.indexOf('  function buttons() {'),js.indexOf('  let savedKeyProviders'));
for(const [,id] of buttons.matchAll(/\$\('([^']+)'\)/g))
  assert.ok(html.includes('id="'+id+'"'),id+' missing from run-control markup');
