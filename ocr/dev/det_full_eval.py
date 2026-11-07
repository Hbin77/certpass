import json, sys, torch
from pathlib import Path
from tarstore import TarStore
from train_det import DetData, DetNet, evaluate
items=[json.loads(l) for l in open("det/boxes.jsonl")]
test=[it for it in items if it["split"]=="test"]
m=DetNet(pretrained=False).cuda(); m.load_state_dict(torch.load("runs/det1/best.pt",map_location="cuda",weights_only=False)["model"])
r=evaluate(m, DetData(test, TarStore(Path("det"),"det_*.tar"), False), "cuda", limit=len(test))
json.dump(r, open("runs/det1/full_test.json","w"), ensure_ascii=False); print(json.dumps(r))
