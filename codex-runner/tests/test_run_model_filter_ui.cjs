const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const setup=require('./helpers/past-runs.cjs');
const run={episode_id:'ep_one',prompt:'Move block',model:'A',started_at:1,xyz:[.1,.2,.3],assessment:{label:'Success',correct:0,incorrect:0,eligibility:'included'}};
test('multi-model filters compose with pagination, search, refresh, robot and view changes',async()=>{
 const c=setup();c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[],null,0,false,['A','B','__unrecorded__']);await c.flush();
 assert.deepEqual(c.nodes.get('pastRunsModel').children.map(row=>row.children[1].textContent),['A','B','Model not recorded']);
 c.choose('A','B');assert.match(c.requests[1].url,/model=A&model=B&view=table/);
 c.answer(c.requests[1],[run],100,101,false,['A','B']);await c.flush();
 assert.match(c.nodes.get('pastRunsList').children[0].children[0].children[0].textContent,/ · A$/);
 c.nodes.get('pastRunsList').children[0].children[0].emit('click');
 c.nodes.get('morePastRuns').emit('click');assert.match(c.requests[2].url,/offset=100.*model=A&model=B/);
 c.nodes.get('pastRunsCloudView').emit('click');assert.match(c.requests[3].url,/offset=0.*model=A&model=B.*view=cloud/);
 c.answer(c.requests[2],[{...run,episode_id:'ep_stale'}]);c.answer(c.requests[3],[run],null,101,false,['A','B']);await c.flush();
 assert.equal(c.cloud.selected,'ep_one');assert.equal(c.cloud.rows[0].episode_id,'ep_one');
 assert.equal(c.storage.get('yam-past-runs-view'),'cloud');
 c.search('block');assert.match(c.requests[4].url,/model=A&model=B&q=block&view=cloud/);
 c.events['blupe-robot-selected']({detail:'so101'});assert.match(c.requests[5].url,/robot_id=so101&model=A&model=B&q=block/);
 c.answer(c.requests[5],[],null,0,false,['Other']);await c.flush();c.choose('');
 assert.doesNotMatch(c.requests[6].url,/[?&]model=/);
});
test('first visit defaults to Table; later visits remember Cloud; Your runs remains above All runs',()=>{
 const first=setup();assert.equal(first.nodes.get('pastRunsTable').hidden,false);assert.equal(first.nodes.get('pastRunsCloud').hidden,true);
 const later=setup('','cloud');assert.equal(later.nodes.get('pastRunsCloud').hidden,false);
 const html=fs.readFileSync(path.join(__dirname,'../static/hosted.html'),'utf8');
 assert.ok(html.indexOf('id="myRunsList"')<html.indexOf('id="pastRunsTableView"'));assert.ok(html.includes('<ol id="pastRunsList">'));
 assert.doesNotMatch(html,/Cards<\/button>/);
});

test('checkbox selection survives local search and catalog refresh; Show all clears only model filtering',async()=>{
 const c=setup('?q=cup','cloud');c.events['blupe-robot-selected']({detail:'yam-1'});
 c.answer(c.requests[0],[],null,0,false,['A','B']);await c.flush();
 const first=c.nodes.get('pastRunsModel').children[0],search=c.nodes.get('pastRunsModelSearch'),count=c.requests.length;
 search.value='b';search.emit('input');assert.equal(first.hidden,true);assert.equal(c.nodes.get('pastRunsModel').children[1].hidden,false);assert.equal(c.requests.length,count,'model-name search stays local');
 c.choose('A','B');assert.equal(c.nodes.get('pastRunsModelValue').textContent,'2 selected');assert.equal(c.nodes.get('pastRunsModelReset').disabled,false);
 assert.match(c.requests.at(-1).url,/model=A&model=B&q=cup&view=cloud/);
 c.answer(c.requests.at(-1),[],null,0,false,['A','B']);await c.flush();assert.equal(c.nodes.get('pastRunsModel').children[0],first,'unchanged choices keep the checkbox and keyboard focus');assert.equal(first.children[0].checked,true);
 search.value='nothing';search.emit('input');assert.equal(c.nodes.get('pastRunsModelEmpty').hidden,false);assert.equal(c.nodes.get('pastRunsModelEmpty').textContent,'No matching models.');
 c.nodes.get('pastRunsModelReset').emit('click');assert.equal(search.value,'');assert.equal(c.nodes.get('pastRunsModelValue').textContent,'All models');assert.equal(c.nodes.get('pastRunsModelReset').disabled,true);
 assert.doesNotMatch(c.requests.at(-1).url,/[?&]model=/);assert.match(c.requests.at(-1).url,/q=cup&view=cloud/);assert.equal(search.focused,true);
});
test('outside click and Escape dismiss the picker without changing selected models',async()=>{
 const c=setup();c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[],null,0,false,['A']);await c.flush();c.choose('A');
 const filter=c.document.getElementById('pastRunsModelFilter'),inside=c.nodes.get('pastRunsModel').children[0].children[0];filter.open=true;filter.contains=target=>target===inside;
 const requests=c.requests.length;c.events.pointerdown({target:inside});assert.equal(filter.open,true);c.events.pointerdown({target:{}});assert.equal(filter.open,false);
 filter.open=true;let prevented=false;c.events.keydown({key:'Escape',preventDefault(){prevented=true}});assert.equal(filter.open,false);assert.equal(prevented,true);assert.equal(c.nodes.get('pastRunsModelSummary').focused,true);
 assert.equal(c.nodes.get('pastRunsModelValue').textContent,'A');assert.equal(c.requests.length,requests);
});
