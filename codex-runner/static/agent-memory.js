"use strict";
// Native details/summary keeps this small addition within the existing task UI.
window.yamAgentMemory = {
  render(provider) {
    let panel = document.getElementById("agentMemoryPanel");
    const memory = provider?.memo;
    if (!memory) { if (panel) panel.hidden = true; return; }
    if (!panel) {
      panel = document.createElement("details");panel.id="agentMemoryPanel";panel.className="agentMemoryPanel";
      const summary=document.createElement("summary");summary.textContent="MEMO skillbook";
      const status=document.createElement("p");status.dataset.memoryStatus="";status.className="help";
      const list=document.createElement("div");list.dataset.memoryList="";
      panel.append(summary,status,list);
      document.getElementById("steeringForm").insertAdjacentElement("afterend",panel);
    }
    panel.hidden=false;
    const status=panel.querySelector("[data-memory-status]");
    status.textContent=memory.enabled
      ? "Version "+(memory.version ?? "pending")+" · "+memory.retrieved.length+" retrieved · "+memory.saved.length+" learned. Skills are agent-authored and unverified."
      : "Skillbook reuse is off. Corrections still guide this run.";
    const list=panel.querySelector("[data-memory-list]"), key=JSON.stringify(memory.saved);
    if(list.dataset.key===key)return;list.dataset.key=key;
    const fragment=document.createDocumentFragment();
    for(const skill of memory.saved){const row=document.createElement("details"),title=document.createElement("summary"),pre=document.createElement("pre");title.textContent=skill.action+" · "+skill.kind+" · v"+skill.version;pre.textContent=skill.content;row.append(title,pre);fragment.append(row);}
    list.replaceChildren(fragment);
  }
};
