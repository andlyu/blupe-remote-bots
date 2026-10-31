
import numpy as np, mujoco, xml.etree.ElementTree as ET, copy
from pathlib import Path
import robokit.assets.robots.assembly.yam_gripper as yam

class Env:
    robot=["robokit.assets.robots.assembly.yam_gripper"]*2
    max_steps=350
    def __init__(self,seed):
        rng=np.random.default_rng(seed)
        root=ET.Element("mujoco",model="Dual official YAM tabletop")
        ET.SubElement(root,"compiler",angle="radian")
        ET.SubElement(root,"option",timestep=".002",integrator="implicitfast",gravity="0 0 -9.81")
        src=ET.parse(Path(__file__).with_name("yam.xml")).getroot()
        root.append(copy.deepcopy(src.find("asset")))
        world=ET.SubElement(root,"worldbody")
        ET.SubElement(world,"geom",name="floor",type="plane",size="3 3 .1",rgba=".32 .35 .37 1")
        ET.SubElement(world,"geom",name="table",type="box",pos="0 0 .72",size=".75 .55 .035",rgba=".48 .29 .14 1")
        for x in [-.64,.64]:
            for y in [-.44,.44]:
                ET.SubElement(world,"geom",type="box",pos=f"{x} {y} .35",size=".035 .035 .35",rgba=".12 .13 .14 1")
        ET.SubElement(world,"geom",type="box",pos="0 1.4 1.4",size="3 .05 1.4",rgba=".76 .78 .74 1")
        act=ET.SubElement(root,"actuator")
        for side,x in [("left",-.32),("right",.32)]:
            b=copy.deepcopy(src.find("worldbody/body"))
            b.set("pos",f"{x} 0 .755")
            for el in b.iter():
                if "name" in el.attrib: el.set("name",side+"_"+el.get("name"))
                if el.tag=="body":
                    el.set("gravcomp","1")
                if el.tag=="joint":
                    el.set("damping","2")
                    el.set("armature",".015")
                    name=el.get("name")
                    ET.SubElement(act,"position",name=name,joint=name,kp="650",kv="45")
                if el.tag=="geom":
                    el.set("contype","1"); el.set("conaffinity","2")
                if el.tag=="geom" and el.get("group")!="1":
                    el.set("rgba",".15 .16 .18 1")
            # Randomized mounting calibration changes physical joint angles while
            # generalized coordinates retain the official REST_Q convention.
            for body in b.iter("body"):
                if body.find("joint") is not None and "tip" not in body.find("joint").get("name",""):
                    old=np.fromstring(body.get("quat","1 0 0 0"),sep=" ")
                    axis=np.fromstring(body.find("joint").get("axis","0 0 1"),sep=" ")
                    a=rng.uniform(-.012,.012)
                    q=np.r_[np.cos(a/2),axis*np.sin(a/2)]
                    out=np.zeros(4); mujoco.mju_mulQuat(out,old,q)
                    body.set("quat"," ".join(map(str,out)))
            # Actual tracked rigid fingertip bodies, fixed to each official finger.
            for name in ["linear_module","linear_module_2"]:
                parent=next(v for v in b.iter("body") if v.get("name")==side+"_"+name)
                ET.SubElement(parent,"body",name=side+"_fingertip_"+name,pos=".006 .006 -.075")
            world.append(b)
        self.model=mujoco.MjModel.from_xml_string(ET.tostring(root).decode())
        self.data=mujoco.MjData(self.model)
        self.names=[mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_JOINT,i) for i in range(self.model.njnt)]
        self.q0=np.array([yam.REST_Q.get(n.split("_",1)[1],0.) for n in self.names])
        self.tips=[mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,s+"_fingertip_"+n) for s in ["left","right"] for n in ["linear_module","linear_module_2"]]
        self.armidx=np.array([i for i,n in enumerate(self.names) if "_joint" in n])
        self.gripidx=np.array([i for i,n in enumerate(self.names) if "_tip" in n])
        self.reset()
    def reset(self):
        mujoco.mj_resetData(self.model,self.data)
        self.data.qpos[:]=self.q0
        self.data.ctrl[:]=self.q0
        mujoco.mj_forward(self.model,self.data)
        self.initial=self.data.xpos[self.tips].copy()
        self.count=0; self.hold=0.; self.raised=False; self.returned=False
        return self.observe()
    def step(self,action=None):
        if action is not None:
            a=np.asarray(action,float)
            if a.shape!=(self.model.nu,): raise ValueError("Action is full joint position target vector.")
            self.data.ctrl[:]=np.clip(a,self.model.jnt_range[:,0],self.model.jnt_range[:,1])
        self.data.ctrl[self.gripidx]=self.q0[self.gripidx]
        for _ in range(10):
            mujoco.mj_step(self.model,self.data)
            delta=self.data.xpos[self.tips]-self.initial
            valid=np.all(np.abs(delta[:,2]-.020)<.0015) and np.all(np.linalg.norm(delta[:,:2],axis=1)<.003)
            unchanged=np.all(np.abs(self.data.qpos[self.gripidx]-self.q0[self.gripidx])<.0005)
            self.hold=self.hold+.002 if valid and unchanged else 0.
            if self.hold>=1.: self.raised=True
            self.returned=bool(self.raised and unchanged and np.all(np.linalg.norm(delta,axis=1)<.0015) and np.max(np.abs(self.data.qvel))<.02)
        self.count+=1
        return self.observe()
    def observe(self):
        return {"robot_q":dict(zip(self.names,map(float,self.data.qpos))),"objects":{mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_BODY,i):list(self.data.xpos[i])+list(self.data.xquat[i]) for i in self.tips}}
    def success(self): return self.returned
    def render(self):
        from rendering import render
        return render(self)
def make(seed): return Env(seed)
