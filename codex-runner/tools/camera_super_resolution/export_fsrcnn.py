from pathlib import Path
import torch
from torch import nn
import onnx,numpy as np,json
from PIL import Image
from read_tf import tensors
root=Path(__file__).resolve().parent
weights,_=tensors(root/'FSRCNN_x2.pb')
class FSRCNN(nn.Module):
    def __init__(self):
        super().__init__();self.layers=nn.ModuleList()
        for i in range(1,9):
            weight=weights[f'f{i}'];h,w,ic,oc=weight.shape
            conv=nn.Conv2d(ic,oc,(h,w),padding=(h//2,w//2),bias=i<8)
            with torch.no_grad():
                conv.weight.copy_(torch.from_numpy(weight.transpose(3,2,0,1)))
                if i<8:conv.bias.copy_(torch.from_numpy(weights[f'b{i}']))
            self.layers.append(conv)
            if i<8:
                activation=nn.PReLU(oc)
                with torch.no_grad():activation.weight.copy_(torch.from_numpy(weights[f'alpha{i}']))
                self.layers.append(activation)
        self.register_buffer('bias',torch.tensor(float(weights['b8'][0])))
    def forward(self,x):
        for layer in self.layers:x=layer(x)
        return torch.nn.functional.pixel_shuffle(x,2)+self.bias
model=FSRCNN().eval();torch.set_num_threads(4)
sample=np.random.default_rng(7).random((1,1,32,48),dtype=np.float32)
# Independent NHWC reference follows the frozen graph's Conv2D/Add/PReLU and
# DepthToSpace operations. This also checks TF-to-Torch weight/channel order.
x=sample.transpose(0,2,3,1)
for i in range(1,9):
    kernel=weights[f'f{i}'];kh,kw,_,_=kernel.shape
    padded=np.pad(x,((0,0),(kh//2,kh//2),(kw//2,kw//2),(0,0)))
    windows=np.lib.stride_tricks.sliding_window_view(padded,(kh,kw),axis=(1,2))
    x=np.einsum('nhwcij,ijco->nhwo',windows,kernel,optimize=True)
    if i<8:
        x=x+weights[f'b{i}']
        x=np.maximum(x,0)+weights[f'alpha{i}']*np.minimum(x,0)
n,h,w,_=x.shape
expected=x.reshape(n,h,w,2,2,1).transpose(0,1,3,2,4,5).reshape(n,h*2,w*2,1)
expected=(expected+weights['b8']).transpose(0,3,1,2)
with torch.inference_mode():actual=model(torch.from_numpy(sample)).numpy()
error=float(np.max(np.abs(expected-actual)))
assert error<3e-5,error
class HalfModel(nn.Module):
    def __init__(self,model):super().__init__();self.model=model.half()
    def forward(self,x):return self.model(x.half()).float()
for half in (False,True):
    filename='fsrcnn-x2-fp16.onnx' if half else 'fsrcnn-x2.onnx'
    torch.onnx.export(HalfModel(model) if half else model,torch.from_numpy(sample),str(root/filename),input_names=['image'],output_names=['enhanced'],
        dynamic_axes={'image':{2:'height',3:'width'},'enhanced':{2:'out_height',3:'out_width'}},opset_version=17,dynamo=False)
print(json.dumps({"reference_max_error":error}))
