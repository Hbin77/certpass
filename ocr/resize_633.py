"""AI Hub 633 화장품 사진을 글자 위치 찾기(검출) 학습용으로 줄인다.

실행(jinusubuntu): python resize_633.py --images VS1.zip --labels VL1.zip --out /data2/hbin/aihub/ai633/det [--long 1280 --workers 4]
- 긴 변을 1280px로 줄인 흑백 JPEG(det_XX.tar)와 단어 사각형 좌표(boxes.jsonl, 줄인 크기 기준)를 만든다
- 분할은 crop_633.py와 같은 사진 이름 해시(평가 10%)라 인식·검출 평가셋이 같은 사진이다
"""
from __future__ import annotations

import argparse
import io
import json
import tarfile
import zipfile
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageOps

from crop_633 import split_of


def work(args):
    shard, items, images_zip, labels_zip, out, long_side = args
    zi, zl = zipfile.ZipFile(images_zip), zipfile.ZipFile(labels_zip)
    lines = []
    with tarfile.open(Path(out) / f"det_{shard:02d}.tar", "w") as tar:
        for img_name, label_name in items:
            ann = json.loads(zl.read(label_name))
            meta = ann["images"][0]
            img = Image.open(io.BytesIO(zi.read(img_name)))
            if (img.width, img.height) != (meta["width"], meta["height"]):
                img = ImageOps.exif_transpose(img)
            s = long_side / max(img.width, img.height)
            img = img.convert("L").resize((round(img.width * s), round(img.height * s)), Image.BILINEAR)
            boxes = []
            for a in ann.get("annotations", []):
                for p in a.get("polygons", []):
                    pts = p.get("points") or []
                    if len(pts) >= 3 and (p.get("text") or "").strip():
                        xs, ys = [q[0] * s for q in pts], [q[1] * s for q in pts]
                        boxes.append([round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)])
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90)
            iid = meta["identifier"]
            ti = tarfile.TarInfo(f"{iid}.jpg")
            ti.size = buf.tell()
            buf.seek(0)
            tar.addfile(ti, buf)
            lines.append(json.dumps({"path": f"{shard:02d}/{iid}.jpg", "w": img.width, "h": img.height,
                                     "split": split_of(iid), "boxes": boxes}, ensure_ascii=False))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--long", type=int, default=1280)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    zi, zl = zipfile.ZipFile(a.images), zipfile.ZipFile(a.labels)
    imgs = {Path(n).stem: n for n in zi.namelist() if "cosmetics" in n and n.lower().endswith((".jpg", ".jpeg", ".png"))}
    pairs = sorted((imgs[Path(n).stem], n) for n in zl.namelist()
                   if "/cosmetics/" in n and n.endswith(".json") and Path(n).stem in imgs)
    chunks = [pairs[i::a.workers] for i in range(a.workers)]
    with Pool(a.workers) as pool:
        res = pool.map(work, [(i, c, a.images, a.labels, str(out), a.long) for i, c in enumerate(chunks)])
    (out / "boxes.jsonl").write_text("\n".join(l for ls in res for l in ls) + "\n", encoding="utf-8")
    print(json.dumps({"images": len(pairs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
