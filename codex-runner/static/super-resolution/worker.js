/* FSRCNN x2 luminance inference. No model inputs or robot controls are changed. */
'use strict';
let session, runtime, inputCanvas, outputCanvas, busy = false;
const MAX_INPUT_PIXELS = 960*540;
async function initialize() {
  const adapter = await navigator.gpu?.requestAdapter();
  if (!adapter) throw Error('WebGPU unavailable');
  importScripts('ort.webgpu.min.js');
  runtime = self.ort;
  runtime.env.wasm.wasmPaths = new URL('.',self.location.href).href;
  runtime.env.wasm.numThreads = 1;
  const model = adapter.features.has('shader-f16')?'fsrcnn-x2-fp16.onnx':'fsrcnn-x2.onnx';
  session = await runtime.InferenceSession.create(new URL(model,self.location.href).href,{
    executionProviders:[{name:'webgpu',preferredLayout:'NHWC'}],graphOptimizationLevel:'all'});
  inputCanvas = new OffscreenCanvas(1,1); outputCanvas = new OffscreenCanvas(1,1);
  self.postMessage({type:'ready'});
}
async function enhance(data) {
  const started = performance.now();
  const scale = Math.min(1,Math.sqrt(MAX_INPUT_PIXELS/(data.bitmap.width*data.bitmap.height)));
  const width = Math.max(1,Math.round(data.bitmap.width*scale));
  const height = Math.max(1,Math.round(data.bitmap.height*scale));
  inputCanvas.width = width; inputCanvas.height = height;
  const ctx = inputCanvas.getContext('2d',{willReadFrequently:true});
  ctx.drawImage(data.bitmap,0,0,width,height); data.bitmap.close();
  const rgba = ctx.getImageData(0,0,width,height).data;
  const luminance = new Float32Array(width*height);
  for (let p=0,i=0;i<luminance.length;i++,p+=4) luminance[i]=(.299*rgba[p]+.587*rgba[p+1]+.114*rgba[p+2])/255;
  const tensor = new runtime.Tensor('float32',luminance,[1,1,height,width]);
  let outputs;
  try {
    outputs = await session.run({image:tensor});
    const y = await outputs.enhanced.getData();
    const w = width*2,h=height*2;
    if(y.length !== w*h || !Number.isFinite(y[0]))throw Error('Invalid model output');
    outputCanvas.width=w;outputCanvas.height=h;
    const output=outputCanvas.getContext('2d',{willReadFrequently:true});
    output.imageSmoothingEnabled=true;output.imageSmoothingQuality='high';
    output.drawImage(inputCanvas,0,0,w,h);
    const pixels=output.getImageData(0,0,w,h),rgb=pixels.data;
    // Replace luma while retaining upscaled source chroma and actual geometry.
    for(let p=0,i=0;i<y.length;i++,p+=4){
      const delta=y[i]*255-(.299*rgb[p]+.587*rgb[p+1]+.114*rgb[p+2]);
      rgb[p]+=delta;rgb[p+1]+=delta;rgb[p+2]+=delta;
    }
    output.putImageData(pixels,0,0);
    const bitmap=outputCanvas.transferToImageBitmap();
    self.postMessage({type:'frame',bitmap,width:w,height:h,started:data.started,
      sequence:data.sequence,elapsed:performance.now()-started},[bitmap]);
  } finally {
    tensor.dispose();if(outputs)for(const value of Object.values(outputs))value.dispose();
  }
}
self.onmessage=async event=>{
  const data=event.data;
  if(busy){data.bitmap?.close();return;}
  busy=true;
  try { if(data.type==='init')await initialize(); else if(data.type==='frame'&&session)await enhance(data); }
  catch {data.bitmap?.close();self.postMessage({type:'error'});}
  finally {busy=false;}
};
