"""Read frozen TensorFlow constant tensors without installing TensorFlow."""
from pathlib import Path
import struct
import numpy as np

def varint(b,i):
    n=0;shift=0
    while True:
        c=b[i];i+=1;n|=(c&127)<<shift
        if c<128:return n,i
        shift+=7

def fields(b):
    i=0
    while i<len(b):
        tag,i=varint(b,i);key,wire=tag>>3,tag&7
        if wire==0:value,i=varint(b,i)
        elif wire==2:
            n,i=varint(b,i);value=b[i:i+n];i+=n
        elif wire==5:value=b[i:i+4];i+=4
        elif wire==1:value=b[i:i+8];i+=8
        else:raise ValueError(wire)
        yield key,value

def tensors(path):
    values={};nodes=[]
    for key,body in fields(Path(path).read_bytes()):
        if key!=1:continue
        items=list(fields(body));node={}
        for k,v in items:
            if k in (1,2):node['name' if k==1 else 'op']=v.decode()
        nodes.append(node)
        if node['op']!='Const':continue
        for k,v in items:
            if k!=5:continue
            attr=dict(fields(v))
            if attr.get(1)!=b'value':continue
            tensor=dict(fields(dict(fields(v))[2]))[8]
            entries=list(fields(tensor));data=dict(entries)
            shape=[]
            for k,v in fields(data.get(2,b'')):
                if k==2:shape.append(dict(fields(v))[1])
            dtype={1:np.float32,3:np.int32}[data[1]]
            if 4 in data:a=np.frombuffer(data[4],dtype=dtype).copy()
            else:
                entries=[v for k,v in entries if k==(5 if dtype==np.float32 else 7)]
                a=np.array([struct.unpack('<f',v)[0] if isinstance(v,bytes) and dtype==np.float32 else v for v in entries],dtype=dtype)
            if a.size==1 and np.prod(shape)>1:a=np.full(shape,a[0],dtype=dtype)
            else:a=a.reshape(shape)
            values[node['name']]=a
    return values,nodes

if __name__=='__main__':
    weights,nodes=tensors(Path(__file__).with_name('FSRCNN_x2.pb'))
    print(nodes)
    for k,v in weights.items():print(k,v.shape,str(v.ravel()[:4]))
