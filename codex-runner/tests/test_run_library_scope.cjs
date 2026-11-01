const test=require('node:test'),assert=require('node:assert/strict');
const setup=require('./helpers/past-runs.cjs');
const robohouse='robot-ba8413962083809c';
const run={episode_id:'ep_roboskills',robot_id:'yam-1',model:'RoboSkills',prompt:'Raise fingertips',started_at:1,xyz:[0,0,0]};

test('default public library discovers RoboSkills independently of the live-control robot',async()=>{
 const c=setup('','cloud',null,false);
 c.events['blupe-robot-selected']({detail:robohouse});
 assert.doesNotMatch(c.requests[0].url,/[?&]robot_id=/);
 assert.equal(c.requests[0].options.headers['X-Blupe-Robot'],robohouse);
 c.answer(c.requests[0],[run],null,1,false,['RoboSkills','Spotter']);await c.flush();
 c.nodes.get('pastRunsModelSearch').value='RoboSkills';c.nodes.get('pastRunsModelSearch').emit('input');
 assert.equal(c.nodes.get('pastRunsModel').children.find(row=>row.children[0].value==='RoboSkills').hidden,false);
 assert.equal(c.nodes.get('pastRunsModelEmpty').hidden,true);
 c.choose('RoboSkills');assert.match(c.requests[1].url,/model=RoboSkills/);assert.doesNotMatch(c.requests[1].url,/robot_id=/);
 c.answer(c.requests[1],[run],null,1,false,['RoboSkills','Spotter']);await c.flush();
 assert.equal(c.cloud.rows[0].robot_id,'yam-1');
 const scope=c.window.yamReplayHistory.dataScope('filtered');
 assert.equal(scope.robot_id,robohouse,'Live-control context stays on Robo-house');
 assert.equal(scope.robot_name,'All robots');assert.equal(scope.library_context.all_robots,true);
 assert.equal(scope.models[0],'RoboSkills');
});

test('explicit history robot filter composes with models and ignores earlier all-robot responses',async()=>{
 const c=setup('','table',null,false);c.events['blupe-robot-selected']({detail:robohouse});
 c.nodes.get('pastRunsRobot').value='yam-1';c.nodes.get('pastRunsRobot').emit('change');
 assert.match(c.requests[1].url,/robot_id=yam-1/);assert.equal(c.requests[1].options.headers['X-Blupe-Robot'],robohouse);
 c.answer(c.requests[0],[{...run,episode_id:'ep_stale'}]);await c.flush();assert.equal(c.nodes.get('pastRunsList').children.length,0);
 c.answer(c.requests[1],[run],null,1,false,['RoboSkills']);await c.flush();c.choose('RoboSkills');
 assert.match(c.requests[2].url,/robot_id=yam-1&model=RoboSkills/);
 const scope=c.window.yamReplayHistory.dataScope('filtered');assert.equal(scope.library_context.robot_id,'yam-1');assert.equal(scope.library_context.all_robots,false);
});

test('global cloud previews use the recording robot and late responses do not seed the changed scope',async()=>{
 const c=setup('','cloud',null,false);c.events['blupe-robot-selected']({detail:robohouse});
 c.answer(c.requests[0],[run]);await c.flush();
 const pending=c.cloudPreview.options.loadRun(run,new AbortController().signal);
 assert.match(c.requests[1].url,/robot_id=yam-1/);assert.equal(c.requests[1].options.headers['X-Blupe-Robot'],'yam-1');
 c.answer(c.requests[1],[{...run,video_url:'/retained.mp4'}]);assert.equal((await pending).video_url,'/retained.mp4');
 c.window.yamReplayHistory.setContextRun(run);assert.ok(c.window.yamReplayHistory.dataScope('run'));
 c.nodes.get('pastRunsRobot').value=robohouse;c.nodes.get('pastRunsRobot').emit('change');
 assert.equal(c.window.yamReplayHistory.dataScope('run'),null);
});
