"""사진 한 장 → 전성분 목록 종단 평가(검출+인식+줄 묶기+전성분 추출+표준명 맞추기).

실행(jinusubuntu, 원본 사진이 있는 곳): python e2e_eval.py --images VS1.zip --labels VL1.zip --unseen test_unseen_product_images.json
    --det det.pt --rec rec.pt --dict 식약처_원료성분사전.csv [--n 150] [--easyocr]
- 대상: 평가셋 중 학습에 없던 제품 사진 가운데, 라벨 글자에 '전성분' 표기가 있는 사진
- 정답 목록: 라벨의 단어(상자+글자)를 같은 줄 묶기·전성분 추출 규칙에 넣어 만든 목록 → 표준 한글명
- 예측 목록: 모델 출력 → 같은 규칙 → 표준 한글명(사전 정확 일치, 없으면 유사도 88 이상)
- 지표: 성분 단위 정밀도·재현율·F1(사진별 집합 비교 합산), 전성분 구역 찾은 비율, 사진당 처리 시간
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageOps
from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import PackageOCR, extract_ingredients, group_lines  # noqa: E402

KEY = re.compile(r"[\s·ㆍ,/()\[\]\-*]")


def load_dict(path: str):
    exact, names = {}, set()
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        for n in [r["kr_name"]] + [x for x in (r.get("synonyms") or "").split("|") if x]:
            if n.strip():
                exact.setdefault(KEY.sub("", n.strip()), r["kr_name"])
        names.add(r["kr_name"])
    return exact, sorted(names)


def standard(raw: str, exact, names):
    k = KEY.sub("", raw)
    if k in exact:
        return exact[k]
    hit = process.extractOne(raw, names, scorer=fuzz.ratio, score_cutoff=88) if len(raw) >= 3 else None
    return hit[0] if hit else None


JUNK = re.compile(r"^[^0-9A-Za-z가-힣(]+|[^0-9A-Za-z가-힣)\]]+$")
LETTER = re.compile(r"[A-Za-z가-힣]")


def segment(chunk: str, exact: dict, max_span: int = 6) -> list[str]:
    """쉼표가 빠져 붙은 덩어리('세테아릴알코올 잔탄검')를 띄어쓰기 단위로 나눠 사전 이름이 가장 많이 맞는 조합으로 쪼갠다.
    줄바꿈으로 잘린 이름('다이프로필렌글 라이콜')은 이어 붙여 찾는다. 사전에 없는 조각은 이어서 하나로 남긴다."""
    toks = [JUNK.sub("", x) for x in chunk.split()]
    toks = [x for x in toks if x][:60]
    n = len(toks)
    best = [(0, -1, False)] + [(-1, -1, False)] * n  # (맞은 개수, 이전 위치, 이번 조각이 사전 이름인가)
    for i in range(1, n + 1):
        for j in range(max(0, i - max_span), i):
            hit = KEY.sub("", "".join(toks[j:i])) in exact
            score = best[j][0] + (1 if hit else 0)
            if hit or i - j == 1:
                if score > best[i][0] or (score == best[i][0] and best[i][1] < 0):
                    best[i] = (score, j, hit)
    pieces, i = [], n
    while i > 0:
        _, j, hit = best[i]
        pieces.append(("".join(toks[j:i]) if hit else " ".join(toks[j:i]), hit))
        i = j
    out, buf = [], []
    for text, hit in reversed(pieces):  # 사전에 없는 조각은 이웃끼리 다시 붙인다
        if hit:
            if buf:
                out.append(" ".join(buf))
                buf = []
            out.append(text)
        else:
            buf.append(text)
    if buf:
        out.append(" ".join(buf))
    return [x for x in out if len(x) >= 2 and LETTER.search(x)]


def standard_set(raw_list, exact, names) -> set[str]:
    out = set()
    for raw in raw_list:
        k = KEY.sub("", JUNK.sub("", raw))
        if k in exact:
            out.add(exact[k])
            continue
        for piece in segment(raw, exact):
            s = standard(piece, exact, names)
            if s:
                out.add(s)
    return out


def words_from_label(ann) -> list[dict]:
    out = []
    for a in ann.get("annotations", []):
        for p in a.get("polygons", []):
            t, pts = (p.get("text") or "").strip(), p.get("points") or []
            if t and len(pts) >= 3:
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                out.append({"box": [min(xs), min(ys), max(xs), max(ys)], "text": t, "conf": 1.0})
    return out


def prf(pairs):
    tp = sum(len(g & p) for g, p in pairs)
    np_, ng = sum(len(p) for _, p in pairs), sum(len(g) for g, _ in pairs)
    pr, rc = tp / max(1, np_), tp / max(1, ng)
    return {"precision": round(pr, 4), "recall": round(rc, 4), "f1": round(2 * pr * rc / max(1e-9, pr + rc), 4),
            "gt_ingredients": ng, "pred_ingredients": np_}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--unseen", required=True)
    ap.add_argument("--det", required=True)
    ap.add_argument("--rec", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--easyocr", action="store_true")
    ap.add_argument("--out", default="e2e_eval.json")
    a = ap.parse_args()
    exact, names = load_dict(a.dict)
    unseen = set(json.loads(Path(a.unseen).read_text(encoding="utf-8")))
    zi, zl = zipfile.ZipFile(a.images), zipfile.ZipFile(a.labels)
    imgs = {Path(n).stem: n for n in zi.namelist() if "cosmetics" in n and n.lower().endswith((".jpg", ".jpeg", ".png"))}
    cases = []
    for n in sorted(zl.namelist()):
        stem = Path(n).stem
        if "/cosmetics/" not in n or not n.endswith(".json") or stem not in unseen or stem not in imgs:
            continue
        ann = json.loads(zl.read(n))
        gt_raw = extract_ingredients(group_lines(words_from_label(ann)))
        gt = standard_set(gt_raw, exact, names)
        if len(gt) >= 5:  # 전성분 구역이 라벨에 있고 사전으로 읽히는 성분이 5개 이상인 사진
            cases.append((stem, imgs[stem], gt))
        if len(cases) >= a.n:
            break
    print(f"평가 사진 {len(cases)}장(학습에 없던 제품, 정답 전성분 5개 이상)", flush=True)
    ours = PackageOCR(a.det, a.rec)
    reader = None
    if a.easyocr:
        import easyocr
        reader = easyocr.Reader(["ko", "en"], gpu=True, verbose=False)
    res = {"ours": [], "easyocr": []}
    times = []
    found = {"ours": 0, "easyocr": 0}
    for stem, name, gt in cases:
        data = zi.read(name)
        t0 = time.time()
        r = ours.read(data)
        times.append(time.time() - t0)
        pred = standard_set(r["ingredients"], exact, names)
        found["ours"] += bool(r["ingredients"])
        res["ours"].append((gt, pred))
        if reader:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            out = reader.readtext(__import__("numpy").asarray(img))
            words = [{"box": [min(p[0] for p in b), min(p[1] for p in b), max(p[0] for p in b), max(p[1] for p in b)],
                      "text": t, "conf": c} for b, t, c in out]
            ing = extract_ingredients(group_lines(words))
            found["easyocr"] += bool(ing)
            res["easyocr"].append((gt, standard_set(ing, exact, names)))
    summary = {"images": len(cases), "ours": {**prf(res["ours"]), "section_found": round(found["ours"] / max(1, len(cases)), 4),
                                              "sec_per_image_gpu": round(sum(times) / max(1, len(times)), 2)}}
    if reader:
        summary["easyocr"] = {**prf(res["easyocr"]), "section_found": round(found["easyocr"] / max(1, len(cases)), 4)}
    Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
