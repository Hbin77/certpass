"""우리 글자 인식 모델을 기준선(EasyOCR)과 같은 평가 단어(sample.tsv)로 잰다.

실행(axgpu): python eval_sample.py --ckpt runs/rec1/best.pt --data crops --sample sample.tsv --ingredients ingredients_kr.txt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from baseline_easyocr import score
from tarstore import TarStore
from train_ocr import OCRNet, Words, collate, greedy, to_input


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--out", default="ours_sample.json")
    a = ap.parse_args()
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    cfg, charset = ck["config"], ck["charset"]
    model = OCRNet(len(charset) + 1, cfg["d"], cfg["layers"], cfg["heads"]).cuda().eval()
    model.load_state_dict(ck["model"])
    rows = [l.split("\t") for l in Path(a.sample).read_text(encoding="utf-8").splitlines() if l]
    ld = DataLoader(Words(rows, TarStore(Path(a.data), "shard_*.tar"), charset, False), batch_size=512, num_workers=0,  # 학습과 동시에 돌 때 /dev/shm(64MB)을 쓰지 않게
                    collate_fn=collate)
    pairs = []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for img, _, _, widths, texts in ld:
            pairs += list(zip(texts, greedy(model(to_input(img, "cuda"), widths).float(), charset, widths)))
    Path(a.out).with_suffix(".pairs.tsv").write_text(
        "\n".join(f"{r[3]}\t{t}\t{p}" for r, (t, p) in zip(rows, pairs)) + "\n", encoding="utf-8")
    ing = {l.strip() for l in Path(a.ingredients).read_text(encoding="utf-8").splitlines() if l.strip()}
    m = score(pairs, ing)
    Path(a.out).write_text(json.dumps({"model": "7팀 포장 OCR(CNN+Transformer+CTC)", **m, "examples": pairs[:40]},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
