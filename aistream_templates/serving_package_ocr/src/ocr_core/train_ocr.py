"""화장품 포장 글자 인식 딥러닝 학습(CNN + Transformer 인코더 + CTC).

실행(axgpu B200): python train_ocr.py --data /data/ocr/crops --out /data/ocr/run1 [--epochs 12 --batch 384]
- 입력: crop_633.py가 만든 shard_XX.tar + labels.tsv (흑백 높이 32px 단어 이미지와 정답 글자)
- 모델: ResNet식 CNN이 이미지를 가로 방향 특징 열로 바꾸고, Transformer 인코더가 앞뒤 문맥을 보고,
  CTC가 글자열로 푼다(글자 위치 정답 없이 단어 정답만으로 학습)
- 평가(사진 단위로 나눈 평가셋): 글자 오류율(CER), 단어 정확도, 성분명처럼 보이는 단어만의 정확도
- 결과: best.pt(가중치·글자표·설정), metrics.json, samples.tsv(틀린 예시)
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import time
from pathlib import Path

import numpy as np

from tarstore import TarStore
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

# 컨테이너의 /dev/shm이 작아(64MB) 작업자→본 프로세스 배치 전달을 파일 방식으로 한다
torch.multiprocessing.set_sharing_strategy("file_system")
torch.backends.cudnn.benchmark = True

H = 32


# ---------------- 데이터 ----------------


class Words(Dataset):
    def __init__(self, rows, blobs, charset, train: bool):
        self.rows, self.blobs, self.train = rows, blobs, train
        self.idx = {c: i + 1 for i, c in enumerate(charset)}  # 0은 CTC 빈칸

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        path, text = self.rows[i][0], self.rows[i][1]
        img = Image.open(io.BytesIO(self.blobs[path])).convert("L")
        if self.train:  # 가벼운 증강: 가로 늘이기·줄이기, 밝기·대비 흔들기
            w = max(8, int(img.width * random.uniform(0.8, 1.2)))
            img = img.resize((min(w, 400), H), Image.BILINEAR)
        x = np.asarray(img, dtype=np.float32) / 255.0
        if self.train:
            x = np.clip((x - 0.5) * random.uniform(0.7, 1.3) + 0.5 + random.uniform(-0.15, 0.15), 0, 1)
        target = [self.idx[c] for c in text if c in self.idx]
        # 작업자→본 프로세스 전달량을 줄이려고 uint8로 넘기고 GPU에서 정규화한다(/dev/shm 64MB)
        return torch.from_numpy((x * 255).astype(np.uint8)), torch.tensor(target, dtype=torch.long), text


def collate(batch):
    xs, ts, texts = zip(*batch)
    W = max(x.shape[1] for x in xs)
    W = (W + 31) // 32 * 32  # 가로를 32 단위로 맞춰 입력 크기 종류를 줄인다(cudnn 자동 튜닝 재사용)
    img = torch.full((len(xs), 1, H, W), 255, dtype=torch.uint8)  # 흰 바탕으로 채움
    for i, x in enumerate(xs):
        img[i, 0, :, : x.shape[1]] = x
    widths = torch.tensor([x.shape[1] for x in xs])
    return img, torch.cat(ts), torch.tensor([len(t) for t in ts]), widths, list(texts)


# ---------------- 모델 ----------------
class Block(nn.Module):
    def __init__(self, cin, cout, stride):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = nn.BatchNorm2d(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = nn.BatchNorm2d(cout)
        self.sc = nn.Sequential() if stride == (1, 1) and cin == cout else nn.Sequential(
            nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

    def forward(self, x):
        return F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x))))) + self.sc(x))


class OCRNet(nn.Module):
    """32×W 흑백 → (W/4)개 특징 열 → Transformer 인코더 → 글자별 확률."""

    def __init__(self, n_class: int, d: int = 384, layers: int = 6, heads: int = 6):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv2d(1, 64, 3, 1, 1, bias=False), nn.BatchNorm2d(64), nn.ReLU())
        self.cnn = nn.Sequential(
            Block(64, 96, (2, 2)), Block(96, 96, (1, 1)),        # 16 × W/2
            Block(96, 192, (2, 2)), Block(192, 192, (1, 1)),     # 8 × W/4
            Block(192, 256, (2, 1)), Block(256, 256, (1, 1)),    # 4 × W/4
            Block(256, d, (2, 1)), Block(d, d, (1, 1)),          # 2 × W/4
        )
        self.pool = nn.AdaptiveAvgPool2d((1, None))
        enc = nn.TransformerEncoderLayer(d, heads, d * 4, dropout=0.1, batch_first=True, norm_first=True)
        # 중첩 텐서 빠른 경로는 CPU 추론에서 입력에 따라 불안정할 수 있어 끈다(가중치 구조는 같음)
        self.tr = nn.TransformerEncoder(enc, layers, enable_nested_tensor=False)
        self.pos = nn.Parameter(torch.zeros(1, 200, d))
        self.head = nn.Linear(d, n_class)

    def forward(self, x, widths=None):
        f = self.pool(self.cnn(self.stem(x))).squeeze(2).transpose(1, 2)  # B × T × d
        T = f.shape[1]
        mask = None
        if widths is not None:
            lens = torch.clamp((widths + 3) // 4, max=T).to(f.device)
            mask = torch.arange(T, device=f.device)[None, :] >= lens[:, None]  # 채움 영역은 주의에서 뺀다
        f = f + self.pos[:, :T]
        return self.head(self.tr(f, src_key_padding_mask=mask))  # B × T × C


# ---------------- 평가 ----------------
def to_input(img, device):
    """uint8 배치 → GPU의 −1~1 실수."""
    return img.to(device, non_blocking=True).float().div_(127.5).sub_(1.0)


def greedy(logits, charset, widths=None):
    """CTC 탐욕 풀기. widths를 주면 단어마다 실제 길이((W+3)//4)까지만 푼다 — 채움 영역은 학습된 적이 없어 엉뚱한 글자가 나온다."""
    out = []
    T = logits.shape[1]
    lens = [T] * logits.shape[0] if widths is None else [min(T, (int(w) + 3) // 4) for w in widths]
    for seq, n in zip(logits.argmax(-1).tolist(), lens):
        s, prev = [], 0
        for k in seq[:n]:
            if k != prev and k != 0:
                s.append(charset[k - 1])
            prev = k
        out.append("".join(s))
    return out


def edit(a: str, b: str) -> int:
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)]


def evaluate(model, loader, charset, device, ingredient_words: set[str], keep_samples=0):
    model.eval()
    n = ok = err = tot = ing_n = ing_ok = 0
    samples = []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for img, _, _, widths, texts in loader:
            pred = greedy(model(to_input(img, device), widths).float(), charset, widths)
            for p, t in zip(pred, texts):
                n += 1
                ok += p == t
                err += edit(p, t)
                tot += max(1, len(t))
                if t.strip(",.;:·()[]") in ingredient_words:  # 포장 표기는 성분 뒤에 쉼표가 붙는다
                    ing_n += 1
                    ing_ok += p == t
                if p != t and len(samples) < keep_samples:
                    samples.append((t, p))
    model.train()
    return {"words": n, "word_acc": round(ok / max(1, n), 4), "cer": round(err / max(1, tot), 4),
            "ingredient_words": ing_n, "ingredient_word_acc": round(ing_ok / max(1, ing_n), 4)}, samples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=384)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="학습 단어 N개만(시험용)")
    ap.add_argument("--d", type=int, default=256)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--eval_limit", type=int, default=30000, help="회차마다 평가할 단어 수(마지막 전체 평가는 따로)")
    ap.add_argument("--bench", type=int, default=0, help="N스텝만 돌려 데이터 대기·계산 시간을 재고 끝낸다")
    ap.add_argument("--ingredients", default="", help="성분명 목록(한 줄에 하나, 한글·INCI). 성분 단어 정확도 계산용")
    a = ap.parse_args()
    torch.manual_seed(0)
    random.seed(0)
    root, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rows = [l.split("\t") for l in (root / "labels.tsv").read_text(encoding="utf-8").splitlines()[1:] if l]
    train = [r for r in rows if r[2] == "train" and len(r[1]) <= 40]
    test = [r for r in rows if r[2] == "test" and len(r[1]) <= 40]
    if a.limit:
        train = train[: a.limit]
        test = test[: max(2000, a.limit // 10)]
    charset = sorted({c for r in train for c in r[1]})
    blobs = TarStore(root, "shard_*.tar")
    print(f"[load] 학습 {len(train)} · 평가 {len(test)} 단어, 글자표 {len(charset)}종, {time.time() - t0:.0f}s", flush=True)
    ing = set()
    if a.ingredients and Path(a.ingredients).exists():
        ing = {l.strip() for l in Path(a.ingredients).read_text(encoding="utf-8").splitlines() if l.strip()}
    device = "cuda"
    # 비슷한 가로 길이끼리 묶어 채움(padding)을 줄인다
    train.sort(key=lambda r: len(r[1]))
    tr_ds, te_ds = Words(train, blobs, charset, True), Words(test, blobs, charset, False)

    def batches():
        idx = list(range(len(train)))
        chunks = [idx[i:i + a.batch] for i in range(0, len(idx), a.batch)]
        random.shuffle(chunks)
        return chunks

    rnd = random.Random(1)
    te_sample = rnd.sample(test, min(a.eval_limit, len(test)))
    te_sm = DataLoader(Words(te_sample, blobs, charset, False), batch_size=512, num_workers=a.workers, collate_fn=collate,
                       pin_memory=True, prefetch_factor=1)
    te_ld = DataLoader(te_ds, batch_size=512, num_workers=a.workers, collate_fn=collate, pin_memory=True, prefetch_factor=1)
    model = OCRNet(len(charset) + 1, a.d, a.layers, a.heads).to(device)
    n_param = sum(p.numel() for p in model.parameters())
    print(f"[model] 파라미터 {n_param / 1e6:.1f}M", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.05)
    steps = a.epochs * math.ceil(len(train) / a.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.05)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    best, history, step = None, [], 0
    for ep in range(1, a.epochs + 1):
        tr_ld = DataLoader(tr_ds, batch_sampler=batches(), num_workers=a.workers, collate_fn=collate, pin_memory=True, prefetch_factor=1)
        te = time.time()
        run = 0.0
        t_data = t_comp = 0.0
        tick = time.time()
        for img, tgt, tlen, widths, _ in tr_ld:
            t_data += time.time() - tick
            tick = time.time()
            img = to_input(img, device)
            tgt, tlen = tgt.to(device, non_blocking=True), tlen.to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(img, widths)
            lp = logits.float().log_softmax(-1).transpose(0, 1)  # T × B × C
            ilen = torch.clamp((widths + 3) // 4, max=lp.shape[0]).to(device)
            loss = ctc(lp, tgt, ilen, tlen)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            sched.step()
            step += 1
            if step % 50 == 0 or step == 1:  # 매 스텝 .item()은 GPU 동기화라 50스텝마다만 읽는다
                run = 0.9 * run + 0.1 * loss.item() if step > 1 else loss.item()
                t_comp += time.time() - tick
            if step % 500 == 0:
                print(f"[train] ep{ep} step {step}/{steps} loss {run:.3f} 데이터대기 {t_data:.0f}s", flush=True)
            if a.bench and step >= a.bench:
                torch.cuda.synchronize()
                print(f"[bench] {step}스텝 {time.time() - te:.1f}s, 데이터 대기 {t_data:.1f}s", flush=True)
                return
            tick = time.time()
        m, samples = evaluate(model, te_sm, charset, device, ing, keep_samples=300)
        m.update(epoch=ep, loss=round(run, 4), epoch_sec=round(time.time() - te))
        history.append(m)
        print(f"[eval] {json.dumps(m, ensure_ascii=False)}", flush=True)
        if best is None or m["cer"] < best["cer"]:
            best = m
            torch.save({"model": model.state_dict(), "charset": charset, "config": {"H": H, "d": a.d, "layers": a.layers, "heads": a.heads}},
                       out / "best.pt")
            (out / "samples.tsv").write_text("정답\t예측\n" + "\n".join(f"{t}\t{p}" for t, p in samples), encoding="utf-8")
        (out / "metrics.json").write_text(json.dumps({"best": best, "history": history, "params_M": round(n_param / 1e6, 1),
                                                      "train_words": len(train), "test_words": len(test)},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    # 최고 가중치로 평가셋 전체를 다시 잰다(보고용 최종 수치)
    model.load_state_dict(torch.load(out / "best.pt", map_location=device, weights_only=False)["model"])
    final, samples = evaluate(model, te_ld, charset, device, ing, keep_samples=500)
    (out / "samples.tsv").write_text("정답\t예측\n" + "\n".join(f"{t}\t{p}" for t, p in samples), encoding="utf-8")
    js = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    js["final_full_test"] = final
    (out / "metrics.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[final] {json.dumps(final, ensure_ascii=False)}", flush=True)
    print(f"[done] best {json.dumps(best, ensure_ascii=False)} 총 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
