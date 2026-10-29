const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const setup=require('./helpers/past-runs.cjs');
const run={episode_id:'ep_one',prompt:'Move block',model:'A',started_at:1,xyz:[.1,.2,.3],assessment:{label:'Success',correct:0,incorrect:0,eligibility:'included'}};
test('multi-model filters compose with pagination, search, refresh, robot and view changes',async()=>{
 const c=setup();c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[],null,0,false,['A','B','__unrecorded__']);await c.flush();
 assert.deepEqual(c.nodes.get('pastRunsModel').children.map(option=>option.textContent),['All models','A','B','Model not recorded']);
 c.choose('A','B');assert.match(c.requests[1].url,/model=A&model=B&view=table/);
 c.answer(c.requests[1],[run],100,101,false,['A','B']);await c.flush();
 assert.equal(c.nodes.get('pastRunsList').children[0].children[1].textContent,'A · version unknown');
 c.nodes.get('pastRunsList').children[0].children[0].children[0].emit('click');
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
 assert.ok(html.indexOf('id="myRunsList"')<html.indexOf('id="pastRunsTableView"'));assert.ok(html.includes('<tbody id="pastRunsList">'));
 assert.doesNotMatch(html,/Cards<\/button>/);
});
