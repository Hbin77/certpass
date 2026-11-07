"""AI Hub 633(의약품·화장품 패키징 OCR)에서 화장품 사진의 단어 상자를 잘라 글자 인식 학습 데이터를 만든다.

실행(jinusubuntu): python crop_633.py --images VS1.zip --labels VL1.zip --out /data2/hbin/aihub/ai633/crops [--workers 4]
- 화장품(cosmetics) 사진만 쓴다. 라벨 JSON의 단어 사각형을 잘라 흑백, 높이 32px(가로세로 비 유지, 최대 가로 400px) JPEG로 저장
- 사진 단위로 학습 90% · 평가 10% 분할(사진 이름 해시로 고정). 같은 사진의 단어가 학습·평가에 섞이지 않는다
- 출력: shard_XX.tar(JPEG 모음) + labels.tsv(파일명, 정답 글자, 분할, 사진 ID)
- AI Hub 이용약관상 원본·파생 데이터는 저장소·공개 서버에 올리지 않는다(학습용 팀 서버에만 둔다)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import time
import zipfile
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageOps

H, MAX_W, PAD = 32, 400, 2


def split_of(image_id: str) -> str:
    return "test" if int(hashlib.md5(image_id.encode()).hexdigest(), 16) % 10 == 0 else "train"


def crops_of(img: Image.Image, ann: dict):
    """라벨의 단어 사각형마다 (정답 글자, 잘라 낸 흑백 이미지)를 낸다. 세로쓰기·너무 작은 상자는 뺀다."""
    for a in ann.get("annotations", []):
        for p in a.get("polygons", []):
            text = (p.get("text") or "").strip()
            pts = p.get("points") or []
            if not text or len(pts) < 3:
                continue
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            x0, y0 = max(0, int(min(xs)) - PAD), max(0, int(min(ys)) - PAD)
            x1, y1 = min(img.width, int(max(xs)) + PAD), min(img.height, int(max(ys)) + PAD)
            w, h = x1 - x0, y1 - y0
            if w < 4 or h < 6 or (h > 1.5 * w and len(text) > 1):
                continue
            c = img.crop((x0, y0, x1, y1))
            nw = max(8, min(MAX_W, round(w * H / h)))
            yield text, c.resize((nw, H), Image.BILINEAR)


def work(args):
    shard, items, images_zip, labels_zip, out = args
    zi, zl = zipfile.ZipFile(images_zip), zipfile.ZipFile(labels_zip)
    rows, n_img, t0 = [], 0, time.time()
    with tarfile.open(Path(out) / f"shard_{shard:02d}.tar", "w") as tar:
        for img_name, label_name in items:
            ann = json.loads(zl.read(label_name))
            meta = ann["images"][0]
            img = Image.open(io.BytesIO(zi.read(img_name)))
            if (img.width, img.height) != (meta["width"], meta["height"]):
                img = ImageOps.exif_transpose(img)  # 라벨 좌표는 회전 보정된 크기 기준
            img = img.convert("L")
            iid = meta["identifier"]
            sp = split_of(iid)
            for k, (text, c) in enumerate(crops_of(img, ann)):
                buf = io.BytesIO()
                c.save(buf, "JPEG", quality=88)
                name = f"{iid}_{k:04d}.jpg"
                ti = tarfile.TarInfo(name)
                ti.size = buf.tell()
                buf.seek(0)
                tar.addfile(ti, buf)
                rows.append(f"{shard:02d}/{name}\t{text.replace(chr(9), ' ')}\t{sp}\t{iid}")
            n_img += 1
            if n_img % 200 == 0:
                print(f"[shard {shard}] {n_img}/{len(items)} 사진, {len(rows)} 단어, {time.time() - t0:.0f}s", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 사진 N장만(시험용)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    zi, zl = zipfile.ZipFile(a.images), zipfile.ZipFile(a.labels)
    imgs = {Path(n).stem: n for n in zi.namelist() if "cosmetics" in n and n.lower().endswith((".jpg", ".jpeg", ".png"))}
    pairs = sorted((imgs[Path(n).stem], n) for n in zl.namelist()
                   if "/cosmetics/" in n and n.endswith(".json") and Path(n).stem in imgs)
    if a.limit:
        pairs = pairs[: a.limit]
    print(f"화장품 사진 {len(imgs)}장, 라벨과 짝 {len(pairs)}장", flush=True)
    chunks = [pairs[i::a.workers] for i in range(a.workers)]
    with Pool(a.workers) as pool:
        results = pool.map(work, [(i, c, a.images, a.labels, str(out)) for i, c in enumerate(chunks)])
    rows = [r for rs in results for r in rs]
    (out / "labels.tsv").write_text("path\ttext\tsplit\timage_id\n" + "\n".join(rows) + "\n", encoding="utf-8")
    n_test = sum(r.split("\t")[2] == "test" for r in rows)
    print(json.dumps({"images": len(pairs), "words": len(rows), "test_words": n_test}, ensure_ascii=False))


if __name__ == "__main__":
    main()
