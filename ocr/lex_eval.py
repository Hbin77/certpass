"""사전 제한 해독 단어 단위 평가: 학습 코드와 같은 평가 표본(깨끗한·망가뜨린)에서 탐욕 풀기 vs 사전 해독.

실행(axgpu): python lex_eval.py --data crops --rec runs/rec4/best.pt --dict 식약처_원료성분사전.csv --n 10000
- 확신도가 낮은 단어마다 후보·우도 차이를 한 번 계산해 두고, 기준(margin·conf_below) 조합별 정확도를 잰다
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lexicon import EDGE, Lexicon
from tarstore import TarStore
from train_ocr import OCRNet, Words, collate, greedy, to_input


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--rec", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--ingredients", default="ingredients_kr.txt")
    ap.add_argument("--n", type=int, default=10000)
    a = ap.parse_args()
    ck = torch.load(a.rec, map_location="cpu", weights_only=False)
    cs, cfg = ck["charset"], ck["config"]
    model = OCRNet(len(cs) + 1, cfg["d"], cfg["layers"], cfg["heads"]).cuda().eval()
    model.load_state_dict(ck["model"])
    root = Path(a.data)
    rows = [ln.split("\t") for ln in (root / "labels.tsv").read_text(encoding="utf-8").splitlines()[1:] if ln]
    test = [r for r in rows if r[2] == "test" and len(r[1]) <= 40]
    te = random.Random(1).sample(test, 30000)[: a.n]  # 학습 코드 평가 표본의 앞부분
    blobs = TarStore(root, "shard_*.tar")
    ing = {ln.strip() for ln in Path(a.ingredients).read_text(encoding="utf-8").splitlines() if ln.strip()}
    lex = Lexicon.from_csv(a.dict, cs, conf_below=1.01)  # 기준은 아래에서 따로 적용
    print(f"사전 단어 {len(lex.words)}개", flush=True)
    out = {}
    for name, deg in (("clean", 0.0), ("degraded", 1.0)):
        ld = DataLoader(Words(te, blobs, cs, False, deg, fixed=True), batch_size=256, num_workers=4, collate_fn=collate)
        recs = []
        with torch.no_grad():
            for img, _, _, widths, texts in ld:
                logits = model(to_input(img, "cuda"), widths).float()
                preds = greedy(logits, cs, widths)
                probs = logits.softmax(-1)
                logp = logits.log_softmax(-1).cpu()
                for k, (p, t) in enumerate(zip(preds, texts)):
                    T = min(logits.shape[1], (int(widths[k]) + 3) // 4)
                    mx = probs[k, :T].max(-1)
                    keep = mx.indices != 0
                    conf = float(mx.values[keep].mean()) if keep.any() else 0.0
                    conf = conf if math.isfinite(conf) else 0.0
                    cand, gap = p, None
                    lead, core, trail = EDGE.match(p).groups() if p else ("", "", "")
                    if p and len(core) >= 3 and all(c in lex.idx for c in p):
                        lex.margin = 1e9  # 후보와 우도 차이만 얻는다
                        c2, changed = lex.correct(p, conf, logp[k, :T])
                        if changed:
                            lls = lex._ll(logp[k, :T], [p, c2])
                            cand, gap = c2, lls[1] - lls[0]
                    recs.append({"t": t, "p": p, "c": cand, "gap": gap, "conf": conf, "ing": t.strip(",.;:·()[]") in ing})
        def acc(sel):
            n = len(recs)
            ok = sum(sel(r) == r["t"] for r in recs)
            ir = [r for r in recs if r["ing"]]
            return round(ok / n, 4), round(sum(sel(r) == r["t"] for r in ir) / max(1, len(ir)), 4)
        res = {"greedy": acc(lambda r: r["p"])}
        for conf_below in (0.9, 0.97, 1.01):
            for margin in (0.0, 1.0, 2.0, 4.0):
                def sel(r, cb=conf_below, m=margin):
                    return r["c"] if r["gap"] is not None and r["conf"] < cb and r["gap"] >= -m else r["p"]
                fixed = sum(sel(r) != r["p"] and sel(r) == r["t"] for r in recs)
                broke = sum(sel(r) != r["p"] and r["p"] == r["t"] for r in recs)
                res[f"conf<{conf_below} margin {margin}"] = {"word_acc,ing_acc": acc(sel), "fixed": fixed, "broke": broke}
        out[name] = res
        print(name, json.dumps(res, ensure_ascii=False), flush=True)
    Path("lex_eval_" + Path(a.rec).parent.name + ".json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
