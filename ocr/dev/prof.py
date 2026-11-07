import time, torch, torch.nn as nn
from train_ocr import OCRNet
dev="cuda"; m=OCRNet(1528).to(dev); opt=torch.optim.AdamW(m.parameters(),1e-3); ctc=nn.CTCLoss(zero_infinity=True)
B,W=384,160
x=torch.randn(B,1,32,W,device=dev); widths=torch.full((B,),W); tg=torch.randint(1,1528,(B*8,),device=dev); tl=torch.full((B,),8,device=dev)
def t(f,n=10):
    torch.cuda.synchronize(); s=time.time()
    for _ in range(n): f()
    torch.cuda.synchronize(); return (time.time()-s)/n
def fwd():
    with torch.autocast("cuda",dtype=torch.bfloat16): return m(x,widths)
print("fwd", t(fwd))
def step():
    with torch.autocast("cuda",dtype=torch.bfloat16): lg=m(x,widths)
    lp=lg.float().log_softmax(-1).transpose(0,1); il=torch.full((B,),lp.shape[0],device=dev)
    loss=ctc(lp,tg,il,tl); opt.zero_grad(); loss.backward(); opt.step()
print("step", t(step))
def step_noctc():
    with torch.autocast("cuda",dtype=torch.bfloat16): lg=m(x,widths)
    loss=lg.float().mean(); opt.zero_grad(); loss.backward(); opt.step()
print("step_noctc", t(step_noctc))
torch.backends.cudnn.benchmark=True
print("step cudnn.benchmark", t(step,5), t(step))
print(torch.backends.cudnn.version(), torch.cuda.get_device_properties(0))
