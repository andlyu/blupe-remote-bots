const {test}=require('node:test');
const assert=require('node:assert/strict');
const {observerClarityCPU}=require('../static/observer-enhancement-worker.js');

test('zero strength preserves every received byte and does not mutate input',()=>{
 const input=Uint8ClampedArray.from({length:8*8*4},(_,i)=>(i*37)%256),saved=new Uint8ClampedArray(input);
 assert.deepEqual(observerClarityCPU(input,8,8,0),saved);assert.deepEqual(input,saved);
});
test('flat black, white and saturated colors remain unchanged including alpha',()=>{
 for(const rgba of [[0,0,0,255],[255,255,255,255],[200,30,40,180],[20,40,190,255]]){
  const input=Uint8ClampedArray.from({length:5*5*4},(_,i)=>rgba[i%4]);
  assert.deepEqual(observerClarityCPU(input,5,5,1),input);
 }
});
test('known midtone edge gains contrast without changing the source',()=>{
 const input=Uint8ClampedArray.from([100,100,100,100,100,130,100,90,100].flatMap(v=>[v,v,v,255]));
 // Center100, ring100/100/130/90: noise=.125 and limited lobe=-.162259615.
 // Resolving this independent test vector rounds the center down to91.
 const actual=observerClarityCPU(input,3,3,1);
 assert.deepEqual([...actual.slice(16,20)],[91,91,91,255]);assert.equal(input[16],100);
});
