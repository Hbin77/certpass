"""표 특징(96열)을 28×28 흑백 이미지로 바꾼다 — AIStream에 표 데이터용 학습 템플릿이 없어 CNN 이미지 분류 템플릿으로 학습하기 위해.

- 특징 하나를 2×2 칸(14×14 격자 중 앞 96칸, 행 우선)에 그린다. 값은 학습 데이터의 열별 최솟값·최댓값으로 0~255에 맞춘다.
- 인코딩 설정(열 순서·최솟값·최댓값)은 data/ml/image_encoding.json에 저장해 서빙 호출 때 같은 변환을 쓴다.

실행: python -m certcheck.image_encode out/public/aistream   → certpass_img_train.zip(클래스 폴더 구조)
"""
from __future__ import annotations

import csv
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

from .data import DATA

SIZE, CELL = 28, 2
GRID = SIZE // CELL  # 14 × 14 = 196칸
ENCODING_FILE = DATA / "ml" / "image_encoding.json"


def fit(train_csv: Path) -> dict:
    with train_csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0] if c != "label"]
    lo = {c: min(float(r[c] or 0) for r in rows) for c in cols}
    hi = {c: max(float(r[c] or 0) for r in rows) for c in cols}
    enc = {"size": SIZE, "cell": CELL, "columns": cols, "min": lo, "max": hi}
    ENCODING_FILE.write_text(json.dumps(enc, ensure_ascii=False), encoding="utf-8")
    return enc


def load() -> dict:
    return json.loads(ENCODING_FILE.read_text(encoding="utf-8"))


def to_pixels(values: list[float], enc: dict) -> bytes:
    """특징 값 목록(enc['columns'] 순서) → 28×28 흑백 픽셀(행 우선 784바이트)."""
    img = bytearray(SIZE * SIZE)
    for i, (col, v) in enumerate(zip(enc["columns"], values)):
        lo, hi = enc["min"][col], enc["max"][col]
        level = 0 if hi <= lo else round(255 * min(1.0, max(0.0, (float(v) - lo) / (hi - lo))))
        gy, gx = divmod(i, GRID)
        for dy in range(CELL):
            start = (gy * CELL + dy) * SIZE + gx * CELL
            img[start:start + CELL] = bytes([level]) * CELL
    return bytes(img)


def to_png(pixels: bytes, size: int = SIZE) -> bytes:
    """의존성 없이 8비트 흑백 PNG를 만든다."""
    raw = b"".join(b"\x00" + pixels[y * size:(y + 1) * size] for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build_zip(folder: Path, split: str = "train") -> Path:
    enc = fit(folder / "train.csv") if split == "train" or not ENCODING_FILE.exists() else load()
    out = folder / f"certpass_img_{split}.zip"
    with (folder / f"{split}.csv").open(encoding="utf-8") as f, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, r in enumerate(csv.DictReader(f)):
            px = to_pixels([float(r[c] or 0) for c in enc["columns"]], enc)
            z.writestr(f"{r['label']}/{split}_{n:06d}.png", to_png(px))
    return out


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    for split in sys.argv[2:] or ["train"]:
        p = build_zip(folder, split)
        print(p, p.stat().st_size)
