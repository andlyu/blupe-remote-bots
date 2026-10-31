export type Pixel = {u:number;v:number};
export type ImageSize = {width:number;height:number};
export type ObjectMarks = {source:Pixel|null;target:Pixel|null};
type Rect = {left:number;top:number;width:number;height:number};

function validSize(size:ImageSize){return Number.isInteger(size.width)&&Number.isInteger(size.height)&&size.width>0&&size.height>0;}
function validPixel(point:Pixel,size:ImageSize){return Number.isInteger(point.u)&&Number.isInteger(point.v)&&point.u>=0&&point.v>=0&&point.u<size.width&&point.v<size.height;}

export function imagePixel(clientX:number,clientY:number,rect:Rect,size:ImageSize):Pixel|null{
 if(!validSize(size)||![clientX,clientY,rect.left,rect.top,rect.width,rect.height].every(Number.isFinite)||rect.width<=0||rect.height<=0)return null;
 const x=clientX-rect.left,y=clientY-rect.top;
 if(x<0||y<0||x>rect.width||y>rect.height)return null;
 return {u:Math.min(size.width-1,Math.floor(x/rect.width*size.width)),v:Math.min(size.height-1,Math.floor(y/rect.height*size.height))};
}

export function keyboardPixel(point:Pixel,key:string,shift:boolean,size:ImageSize):Pixel|null{
 if(!validSize(size)||!validPixel(point,size))return null;
 const step=shift?10:1;
 if(key==='Home')return {u:0,v:0};
 if(key==='End')return {u:size.width-1,v:size.height-1};
 const change:Record<string,[number,number]>={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]};
 if(!Object.hasOwn(change,key))return null;
 return {u:Math.max(0,Math.min(size.width-1,point.u+change[key][0])),v:Math.max(0,Math.min(size.height-1,point.v+change[key][1]))};
}

export function markedInstruction(instruction:string,marks:ObjectMarks,size:ImageSize,required=true):string{
 const task=instruction.trim();
 if(!marks.source&&!marks.target&&!required)return task;
 if(!marks.source||!marks.target)throw Error('Mark both the source and target in the top camera before joining the queue.');
 if(!validSize(size)||!validPixel(marks.source,size)||!validPixel(marks.target,size))throw Error('The camera marks are invalid. Clear them and select the objects again.');
 if(marks.source.u===marks.target.u&&marks.source.v===marks.target.v)throw Error('Choose different source and target points.');
 const result=task+'\n\nMarked objects in the reference top image ('+size.width+'x'+size.height+' pixels): SOURCE=('+marks.source.u+','+marks.source.v+'), TARGET=('+marks.target.u+','+marks.target.v+'). These are operator-selected reference pixels. Verify the objects against the fresh scene after admission, map the reference pixels if the image resolution differs, and measure depth before motion. Re-localize if the objects have moved.';
 if(result.length>3000)throw Error('Shorten the task so it fits with the camera marks (3000 characters total).');
 return result;
}
