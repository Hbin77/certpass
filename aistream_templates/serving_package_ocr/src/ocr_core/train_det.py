"""화장품 포장 사진에서 단어 위치를 찾는 검출 딥러닝 학습(ResNet18 + FPN 분할, DBNet 방식의 축소 영역 학습).

실행(axgpu B200): python train_det.py --data /data/ocr/det --out /data/ocr/det_run1 [--epochs 30 --batch 16]
- 입력: resize_633.py가 만든 det_XX.tar(긴 변 1280px 흑백) + boxes.jsonl(단어 사각형)
- 정답 지도: 단어 사각형을 DBNet 공식(d = 넓이×(1−r²)/둘레, r=0.4)만큼 안쪽으로 줄인 영역 = 1
- 예측 후처리: 확률 0.3 이상 영역의 연결 요소마다 상자를 구하고 같은 공식으로 다시 넓힌다
- 평가(사진 단위 평가셋, crop_633과 같은 분할): IoU 0.5 기준 정밀도·재현율·F1
"""
from __future__ import annotations

import argparse
import io
import json
import random
import time
from pathlib import Path

import numpy as np

from tarstore import TarStore
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from scipy import ndimage
from torch.utils.data import DataLoader, Dataset

# 컨테이너의 /dev/shm이 작아(64MB) 작업자→본 프로세스 배치 전달을 파일 방식으로 한다
torch.multiprocessing.set_sharing_strategy("file_system")
from torchvision.models import ResNet18_Weights, resnet18

R, CROP = 0.4, 640




def shrink_map(h, w, boxes, ratio=R):
    m = np.zeros((h, w), np.float32)
    for x0, y0, x1, y1 in boxes:
        bw, bh = x1 - x0, y1 - y0
        if bw < 2 or bh < 2:
            continue
        d = bw * bh * (1 - ratio ** 2) / (2 * (bw + bh))
        a0, b0, a1, b1 = int(x0 + d), int(y0 + d), int(np.ceil(x1 - d)), int(np.ceil(y1 - d))
        if a1 > a0 and b1 > b0:
            m[max(0, b0):b1, max(0, a0):a1] = 1
    return m


class DetData(Dataset):
    def __init__(self, items, blobs, train):
        self.items, self.blobs, self.train = items, blobs, train

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        it = self.items[i]
        img = np.asarray(Image.open(io.BytesIO(self.blobs[it["path"]])).convert("L"), np.float32) / 255.0
        boxes = np.array(it["boxes"], np.float32).reshape(-1, 4)
        if self.train:
            s = random.uniform(0.6, 1.4)  # 글자 크기 다양화
            h, w = img.shape
            img = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize((max(1, int(w * s)), max(1, int(h * s)))),
                             np.float32) / 255.0
            boxes = boxes * s
            h, w = img.shape
            ph, pw = max(h, CROP), max(w, CROP)
            canvas = np.ones((ph, pw), np.float32)
            canvas[:h, :w] = img
            # 글자가 있는 곳을 더 자주 자르도록 상자 하나를 중심으로 고른다
            if len(boxes) and random.random() < 0.8:
                b = boxes[random.randrange(len(boxes))]
                cx, cy = int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)
                x0 = int(np.clip(cx - CROP // 2 + random.randint(-200, 200), 0, pw - CROP))
                y0 = int(np.clip(cy - CROP // 2 + random.randint(-200, 200), 0, ph - CROP))
            else:
                x0, y0 = random.randint(0, pw - CROP), random.randint(0, ph - CROP)
            img = canvas[y0:y0 + CROP, x0:x0 + CROP]
            boxes = boxes - np.array([x0, y0, x0, y0], np.float32)
            boxes = boxes[(boxes[:, 2] > 0) & (boxes[:, 3] > 0) & (boxes[:, 0] < CROP) & (boxes[:, 1] < CROP)]
            boxes = np.clip(boxes, 0, CROP)
            img = np.clip((img - 0.5) * random.uniform(0.7, 1.3) + 0.5 + random.uniform(-0.15, 0.15), 0, 1)
        else:
            h, w = img.shape
            ph, pw = (h + 31) // 32 * 32, (w + 31) // 32 * 32
            canvas = np.ones((ph, pw), np.float32)
            canvas[:h, :w] = img
            img = canvas
        gt = shrink_map(img.shape[0], img.shape[1], boxes)
        # /dev/shm(64MB)이 작아 uint8로 넘기고 GPU에서 정규화한다
        return torch.from_numpy((img * 255).astype(np.uint8))[None], torch.from_numpy(gt.astype(np.uint8))[None], i


class DetNet(nn.Module):
    def __init__(self, pretrained=True):
        super().__init__()
        r = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
        self.stem = nn.Sequential(r.conv1, r.bn1, r.relu, r.maxpool)
        self.l1, self.l2, self.l3, self.l4 = r.layer1, r.layer2, r.layer3, r.layer4
        self.lat = nn.ModuleList([nn.Conv2d(c, 128, 1) for c in (64, 128, 256, 512)])
        self.smooth = nn.Conv2d(512, 128, 3, padding=1)
        self.head = nn.Sequential(nn.BatchNorm2d(128), nn.ReLU(), nn.ConvTranspose2d(128, 64, 2, 2), nn.BatchNorm2d(64),
                                  nn.ReLU(), nn.ConvTranspose2d(64, 1, 2, 2))

    def forward(self, x):
        x = x.repeat(1, 3, 1, 1)  # 흑백 → ImageNet 사전학습 가중치의 3채널
        c1 = self.l1(self.stem(x))
        c2 = self.l2(c1)
        c3 = self.l3(c2)
        c4 = self.l4(c3)
        p4 = self.lat[3](c4)
        p3 = self.lat[2](c3) + F.interpolate(p4, size=c3.shape[2:])
        p2 = self.lat[1](c2) + F.interpolate(p3, size=c2.shape[2:])
        p1 = self.lat[0](c1) + F.interpolate(p2, size=c1.shape[2:])
        size = c1.shape[2:]
        f = torch.cat([p1] + [F.interpolate(p, size=size) for p in (p2, p3, p4)], 1)
        return self.head(self.smooth(f))  # 입력 크기 확률 지도(로짓)


def boxes_from_map(prob, thr=0.3, min_area=6):
    lab, n = ndimage.label(prob > thr)
    out = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        bw, bh = x1 - x0, y1 - y0
        if bw * bh < min_area:
            continue
        d = bw * bh * 1.5 / (2 * (bw + bh))  # 축소 영역을 원래 크기로 넓힘
        out.append([x0 - d, y0 - d, x1 + d, y1 + d])
    return out


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1e-6, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def match(pred, gt, thr=0.5):
    used, tp = set(), 0
    for p in pred:
        best, bj = 0, -1
        for j, g in enumerate(gt):
            if j not in used:
                v = iou(p, g)
                if v > best:
                    best, bj = v, j
        if best >= thr:
            used.add(bj)
            tp += 1
    return tp


def evaluate(model, ds, device, limit=400):
    model.eval()
    tp = npred = ngt = 0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for k in range(min(limit, len(ds))):
            x, _, i = ds[k]
            prob = torch.sigmoid(model(x[None].to(device).float().div_(127.5).sub_(1.0)).float())[0, 0].cpu().numpy()
            pred = boxes_from_map(prob)
            gt = ds.items[i]["boxes"]
            tp += match(pred, gt)
            npred += len(pred)
            ngt += len(gt)
    model.train()
    p, r = tp / max(1, npred), tp / max(1, ngt)
    return {"images": min(limit, len(ds)), "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / max(1e-9, p + r), 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--eval_images", type=int, default=400)
    a = ap.parse_args()
    torch.manual_seed(0)
    random.seed(0)
    root, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    items = [json.loads(l) for l in (root / "boxes.jsonl").read_text(encoding="utf-8").splitlines() if l]
    train = [it for it in items if it["split"] == "train"]
    test = [it for it in items if it["split"] == "test"]
    blobs = TarStore(root, "det_*.tar")
    print(f"[load] 학습 {len(train)}장 · 평가 {len(test)}장, {time.time() - t0:.0f}s", flush=True)
    device = "cuda"
    model = DetNet().to(device)
    tr_ds, te_ds = DetData(train, blobs, True), DetData(test, blobs, False)
    ld = DataLoader(tr_ds, batch_size=a.batch, shuffle=True, num_workers=a.workers, drop_last=True, pin_memory=True,
                    persistent_workers=True, prefetch_factor=1)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(ld), pct_start=0.05)
    best, history = None, []
    for ep in range(1, a.epochs + 1):
        te, run = time.time(), 0.0
        for k, (x, gt, _) in enumerate(ld):
            x = x.to(device, non_blocking=True).float().div_(127.5).sub_(1.0)
            gt = gt.to(device, non_blocking=True).float()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logit = model(x)
            logit = logit.float()
            prob = torch.sigmoid(logit)
            bce = F.binary_cross_entropy_with_logits(logit, gt)
            dice = 1 - (2 * (prob * gt).sum() + 1) / (prob.sum() + gt.sum() + 1)
            loss = bce + dice
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            run = loss.item() if k == 0 and ep == 1 else 0.98 * run + 0.02 * loss.item()
        m = evaluate(model, te_ds, device, a.eval_images)
        m.update(epoch=ep, loss=round(run, 4), epoch_sec=round(time.time() - te))
        history.append(m)
        print(f"[eval] {json.dumps(m, ensure_ascii=False)}", flush=True)
        if best is None or m["f1"] > best["f1"]:
            best = m
            torch.save({"model": model.state_dict(), "config": {"ratio": R, "thr": 0.3}}, out / "best.pt")
        (out / "metrics.json").write_text(json.dumps({"best": best, "history": history, "train_images": len(train),
                                                      "test_images": len(test)}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(f"[done] best {json.dumps(best, ensure_ascii=False)} 총 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
