// CPU port of the noise-aware RCAS shader in hosted.js. Same AMD MIT notice.
// https://github.com/GPUOpen-Effects/FidelityFX-FSR/blob/master/license.txt
/*
Copyright (c) 2021 Advanced Micro Devices, Inc. All rights reserved.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/
function observerClarityCPU(input, width, height, strength) {
  const output = new Uint8ClampedArray(input);
  const amount = Math.max(0, Math.min(1, strength));
  if (!amount) return output;
  const stride = width * 4;
  const luma = i => input[i]*.5 + input[i+1] + input[i+2]*.5;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const e = y*stride+x*4;
      const b = y ? e-stride : e, h = y+1<height ? e+stride : e;
      const d = x ? e-4 : e, f = x+1<width ? e+4 : e;
      let lobe = -.1875;
      for (let c = 0; c < 3; c++) {
        const lo = Math.min(input[b+c],input[d+c],input[f+c],input[h+c]);
        const hi = Math.max(input[b+c],input[d+c],input[f+c],input[h+c]);
        const minimum = Math.min(lo,input[e+c])/Math.max(4*hi,.0255);
        const maximum = (255-Math.max(hi,input[e+c]))/Math.min(4*lo-1020,-.0255);
        lobe = Math.max(lobe,-minimum,maximum);
      }
      const bl=luma(b),dl=luma(d),el=luma(e),fl=luma(f),hl=luma(h);
      const span=Math.max(bl,dl,el,fl,hl)-Math.min(bl,dl,el,fl,hl);
      const noise=Math.min(1,Math.abs((bl+dl+fl+hl)*.25-el)/Math.max(span,.0255));
      lobe=Math.min(lobe,0)*amount*(1-.5*noise);
      const divisor=1+4*lobe;
      for(let c=0;c<3;c++)output[e+c]=(input[e+c]+lobe*(input[b+c]+input[d+c]+input[f+c]+input[h+c]))/divisor;
    }
  }
  return output;
}
if (typeof self !== 'undefined') self.onmessage = ({data}) => {
  const started=performance.now();
  const enhanced=observerClarityCPU(data.original,data.width,data.height,data.strength);
  self.postMessage({...data,enhanced,workerMs:performance.now()-started},[data.original.buffer,enhanced.buffer]);
};
if (typeof module !== 'undefined') module.exports = {observerClarityCPU};
