const {test}=require('node:test');
const assert=require('node:assert/strict');
const size={width:640,height:360},rect={left:80,top:120,width:320,height:180};
const load=()=>import('../lib/physical-object-marks.mts');
test('responsive image coordinates use the actual picture, including endpoints',async()=>{
 const {imagePixel}=await load();
 assert.deepEqual(imagePixel(80,120,rect,size),{u:0,v:0});
 assert.deepEqual(imagePixel(400,300,rect,size),{u:639,v:359});
 assert.deepEqual(imagePixel(290.5,217.5,rect,size),{u:421,v:195});
 assert.deepEqual(imagePixel(501,395,{left:80,top:200,width:640,height:360},size),{u:421,v:195});
});
test('letterbox and invalid image coordinates never create a mark',async()=>{
 const {imagePixel}=await load();
 for(const point of [[79,120],[401,120],[100,119],[100,301],[NaN,140],[Infinity,140]])assert.equal(imagePixel(...point,rect,size),null);
 assert.equal(imagePixel(100,140,{...rect,width:0},size),null);
 assert.equal(imagePixel(100,140,rect,{width:0,height:360}),null);
});
test('keyboard selection supports precise and ten-pixel movement without leaving the image',async()=>{
 const {keyboardPixel}=await load();
 assert.deepEqual(keyboardPixel({u:320,v:180},'ArrowRight',true,size),{u:330,v:180});
 assert.deepEqual(keyboardPixel({u:420,v:195},'ArrowRight',false,size),{u:421,v:195});
 assert.deepEqual(keyboardPixel({u:0,v:0},'ArrowLeft',true,size),{u:0,v:0});
 assert.deepEqual(keyboardPixel({u:639,v:359},'ArrowDown',true,size),{u:639,v:359});
 assert.deepEqual(keyboardPixel({u:421,v:195},'Home',false,size),{u:0,v:0});
 assert.deepEqual(keyboardPixel({u:421,v:195},'End',false,size),{u:639,v:359});
 assert.equal(keyboardPixel({u:320,v:180},'a',false,size),null);
});
test('the submitted instruction names the actual selected top-camera pixels',async()=>{
 const {markedInstruction}=await load();
 const value=markedInstruction('Place the source on the target.',{source:{u:421,v:195},target:{u:330,v:109}},size);
 assert.match(value,/640x360 pixels/);assert.match(value,/SOURCE=\(421,195\), TARGET=\(330,109\)/);
 assert.match(value,/fresh scene after admission/);assert.match(value,/measure depth before motion/);
 assert.equal(markedInstruction(' Lift both arms. ',{source:null,target:null},size,false),'Lift both arms.');
});
test('missing, malformed, identical or stale-resolution marks block instruction creation',async()=>{
 const {markedInstruction}=await load();
 for(const marks of [{source:null,target:null},{source:{u:10,v:20},target:null},{source:{u:-1,v:20},target:{u:30,v:40}},{source:{u:640,v:20},target:{u:30,v:40}},{source:{u:10.5,v:20},target:{u:30,v:40}},{source:{u:NaN,v:20},target:{u:30,v:40}},{source:{u:10,v:20},target:{u:10,v:20}}])assert.throws(()=>markedInstruction('Place objects.',marks,size));
 assert.throws(()=>markedInstruction('Place objects.',{source:{u:421,v:195},target:{u:330,v:109}},{width:320,height:180}));
});
test('camera hints never silently truncate the task',async()=>{
 const {markedInstruction}=await load();
 assert.throws(()=>markedInstruction('x'.repeat(2999),{source:{u:421,v:195},target:{u:330,v:109}},size),/Shorten the task/);
});
