"""기준선: 공개 범용 OCR(EasyOCR 한·영 인식 모델)이 같은 평가 단어를 얼마나 읽는지 잰다.

실행(jinusubuntu): python baseline_easyocr.py --data /data2/hbin/aihub/ai633/crops --n 5000 --ingredients ingredients_kr.txt
- 평가셋(test)에서 시드 1로 N단어를 뽑아 sample.tsv로 저장한다 → 우리 모델도 같은 단어로 잰다(eval_sample.py)
- 검출은 빼고 인식만 비교한다(단어 상자 전체를 그대로 준다)
"""
from __future__ import annotations

import argparse
import json
import random
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image
import io


def edit(a: str, b: str) -> int:
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)]


def score(pairs, ing):
    n = len(pairs)
    ok = sum(p == t for t, p in pairs)
    err = sum(edit(p, t) for t, p in pairs)
    tot = sum(max(1, len(t)) for t, _ in pairs)
    ing_pairs = [(t, p) for t, p in pairs if t.strip(",.;:·()[]") in ing]
    # 성분 단어는 포장의 쉼표·마침표 차이를 빼고 비교(성분명 자체를 맞혔는지)
    ing_ok = sum(p.strip(",.;:·()[]") == t.strip(",.;:·()[]") for t, p in ing_pairs)
    return {"words": n, "word_acc": round(ok / n, 4), "cer": round(err / tot, 4),
            "ingredient_words": len(ing_pairs), "ingredient_name_acc": round(ing_ok / max(1, len(ing_pairs)), 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--out", default="baseline_easyocr.json")
    a = ap.parse_args()
    root = Path(a.data)
    rows = [l.split("\t") for l in (root / "labels.tsv").read_text(encoding="utf-8").splitlines()[1:] if l]
    test = [r for r in rows if r[2] == "test" and len(r[1]) <= 40]
    sample = random.Random(1).sample(test, a.n)
    (root.parent / "sample.tsv").write_text("\n".join("\t".join(r) for r in sample) + "\n", encoding="utf-8")
    ing = {l.strip() for l in Path(a.ingredients).read_text(encoding="utf-8").splitlines() if l.strip()}
    want = {r[0] for r in sample}
    blobs = {}
    for tp in sorted(root.glob("shard_*.tar")):
        shard = tp.stem.split("_")[1]
        with tarfile.open(tp) as tar:
            for m in tar:
                key = f"{shard}/{m.name}"
                if key in want:
                    blobs[key] = tar.extractfile(m).read()
    import easyocr
    reader = easyocr.Reader(["ko", "en"], gpu=True, verbose=False)
    pairs = []
    for r in sample:
        img = np.asarray(Image.open(io.BytesIO(blobs[r[0]])).convert("L"))
        h, w = img.shape
        res = reader.recognize(img, horizontal_list=[[0, w, 0, h]], free_list=[], detail=0)
        pairs.append((r[1], "".join(res).replace(" ", "")))
    # 단어별 결과 전부(사진 ID 포함) — 학습에 없던 제품만 따로 재는 데 쓴다
    Path(a.out).with_suffix(".pairs.tsv").write_text(
        "\n".join(f"{r[3]}\t{t}\t{p}" for r, (t, p) in zip(sample, pairs)) + "\n", encoding="utf-8")
    m = score(pairs, ing)
    Path(a.out).write_text(json.dumps({"model": "EasyOCR ko+en (공개 범용)", **m,
                                       "examples": pairs[:40]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
