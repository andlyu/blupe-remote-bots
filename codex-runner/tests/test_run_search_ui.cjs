const test=require('node:test'),assert=require('node:assert/strict');
const setup=require('./helpers/past-runs.cjs');
const run={episode_id:'ep_marker',episode_index:1,robot_id:'yam-1',prompt:'Pick up a marker',model:'M',started_at:1,
 search_match:{exact:[],related:[{query:'pen',match:'marker'}],partial:true}};
test('Table search ranks through server query, explains related/partial matches, and opens shared replay',async()=>{
 const c=setup();c.events['blupe-robot-selected']({detail:'yam-1'});c.search(' put pens into a cup ');
 assert.match(c.requests[1].url,/offset=0&robot_id=yam-1&q=put%20pens%20into%20a%20cup&view=table/);
 c.answer(c.requests[0]);await c.flush();assert.equal(c.nodes.get('pastRunsStatus').textContent,'Loading past runs…');
 c.answer(c.requests[1],[run],100,101);await c.flush();
 assert.match(c.nodes.get('pastRunsStatus').textContent,/101 matching videos.*closest task prompts first/);
 const block=c.nodes.get('pastRunsList').children[0],task=block.children[0];
 assert.match(block.children[1].textContent,/Related: pen → marker · Partial task match/);
 task.emit('click');assert.equal(c.opened[0].id,'ep_marker');
 c.nodes.get('morePastRuns').emit('click');assert.match(c.requests[2].url,/offset=100.*q=put%20pens/);
 c.nodes.get('clearPastRunsSearch').emit('click');assert.doesNotMatch(c.requests[3].url,/[?&]q=/);
 c.answer(c.requests[2],[run]);await c.flush();assert.equal(c.nodes.get('pastRunsList').children.length,0);
 c.answer(c.requests[3]);await c.flush();assert.equal(c.nodes.get('pastRunsStatus').textContent,'No published runs yet.');
});
test('stale query/robot responses cannot replace current rows and errors remain refreshable',async()=>{
 const c=setup();c.events['blupe-robot-selected']({detail:'yam-1'});c.search('markers');c.search('cups');
 c.answer(c.requests[1],[run]);await c.flush();assert.equal(c.nodes.get('pastRunsList').children.length,0);
 c.events['blupe-robot-selected']({detail:'so101'});assert.match(c.requests[3].url,/robot_id=so101&q=cups/);
 c.answer(c.requests[2],[run]);c.answer(c.requests[3],[],null,0,true);await c.flush();
 assert.match(c.nodes.get('pastRunsStatus').textContent,/No matching videos.*saved results/);
 c.search('pen & cup');assert.match(c.requests[4].url,/q=pen%20%26%20cup/);c.requests[4].resolve({ok:false});await c.flush();
 assert.match(c.nodes.get('pastRunsStatus').textContent,/temporarily unavailable/);c.nodes.get('refreshPastRuns').emit('click');
 assert.match(c.requests[5].url,/offset=0.*q=pen%20%26%20cup/);
});
test('shared apple link initializes task search and composes with multiple models',async()=>{
 const c=setup('?q=apple');c.events['blupe-robot-selected']({detail:'yam-1'});
 assert.equal(c.nodes.get('pastRunsQuery').value,'apple');assert.match(c.requests[0].url,/q=apple/);
 c.answer(c.requests[0],[],null,0,false,['A','B']);await c.flush();c.choose('A','B');
 assert.match(c.requests[1].url,/model=A&model=B&q=apple/);
});
