"""포장 사진 한 장 → 단어 위치 찾기(검출) → 글자 읽기(인식) → 줄 묶기 → 전성분 목록.

서빙(AIStream)과 시험에서 함께 쓴다. 가중치는 train_det.py·train_ocr.py의 best.pt.
- 검출은 긴 변 1280px로 줄인 사본에서 하고, 상자를 원본 크기로 되돌려 원본에서 단어를 잘라 읽는다(학습과 같은 해상도)
- 단어마다 확신도(글자별 최대 확률의 평균)를 같이 돌려준다
- 사전(lexicon)을 주면 확신도가 낮은 단어를 성분명 사전으로 다시 푼다(lexicon.py, 고친 단어는 raw에 원래 글자)
"""
from __future__ import annotations

import io
import math
import re

import numpy as np
import torch
from PIL import Image, ImageOps

from train_det import DetNet, boxes_from_map
from train_ocr import H, OCRNet, greedy

DET_LONG = 1280
# 전성분 시작·끝을 알리는 포장 문구(한·영)
START = re.compile(r"(전\s*성\s*분|INGREDIENTS?|Ingredients?)\s*[:：]?")
STOP = re.compile(r"(사용\s*(방법|법|시의|상의)|주의\s*사항|용\s*량|내\s*용\s*량|제조\s*(업자|번호|국)|책임\s*판매|품질\s*보증|"
                  r"사용\s*기한|개봉\s*후|How to use|Caution|Directions|Made in)", re.I)


class PackageOCR:
    def __init__(self, det_ckpt: str, rec_ckpt: str, device: str | None = None, lexicon: str | None = None, **lex_kw):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if hasattr(torch.backends, "mha") and hasattr(torch.backends.mha, "set_fastpath_enabled"):
            torch.backends.mha.set_fastpath_enabled(False)  # 주의 연산 빠른 경로 끔(서빙 CPU에서 입력에 따라 실패 방지)
        d = torch.load(det_ckpt, map_location="cpu", weights_only=False)
        self.det = DetNet(pretrained=False)
        self.det.load_state_dict(d["model"])
        self.det_thr = d["config"].get("thr", 0.3)
        r = torch.load(rec_ckpt, map_location="cpu", weights_only=False)
        cfg = r["config"]
        self.charset = r["charset"]
        self.rec = OCRNet(len(self.charset) + 1, cfg["d"], cfg["layers"], cfg["heads"])
        self.rec.load_state_dict(r["model"])
        self.det.to(self.device).eval()
        self.rec.to(self.device).eval()
        self.lex = None
        if lexicon:
            from lexicon import Lexicon  # rapidfuzz가 필요해 사전을 쓸 때만 읽는다
            self.lex = Lexicon.from_csv(lexicon, self.charset, **lex_kw)

    @torch.no_grad()
    def detect(self, img: Image.Image) -> list[list[float]]:
        s = DET_LONG / max(img.width, img.height)
        small = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.BILINEAR)
        a = np.asarray(small, np.float32) / 255.0
        ph, pw = (a.shape[0] + 31) // 32 * 32, (a.shape[1] + 31) // 32 * 32
        canvas = np.ones((ph, pw), np.float32)
        canvas[: a.shape[0], : a.shape[1]] = a
        x = torch.from_numpy((canvas - 0.5) / 0.5)[None, None].to(self.device)
        prob = torch.sigmoid(self.det(x).float())[0, 0].cpu().numpy()[: a.shape[0], : a.shape[1]]
        out = []
        for b in boxes_from_map(prob, self.det_thr):
            # 넓힌 상자가 사진 밖으로 나가지 않게 자른다(가장자리 글자)
            x0, y0 = max(0.0, b[0] / s), max(0.0, b[1] / s)
            x1, y1 = min(float(img.width), b[2] / s), min(float(img.height), b[3] / s)
            if x1 - x0 >= 2 and y1 - y0 >= 2:
                out.append([x0, y0, x1, y1])
        return out

    @torch.no_grad()
    def recognize(self, img: Image.Image, boxes, batch: int = 64):
        crops = []
        for x0, y0, x1, y1 in boxes:
            x0, y0 = max(0, int(x0) - 2), max(0, int(y0) - 2)
            x1, y1 = min(img.width, int(x1) + 2), min(img.height, int(y1) + 2)
            c = img.crop((x0, y0, x1, y1))
            w = max(8, min(400, round(c.width * H / max(1, c.height))))
            crops.append(np.asarray(c.resize((w, H), Image.BILINEAR), np.float32) / 255.0)
        out = []
        for i in range(0, len(crops), batch):
            part = crops[i:i + batch]
            W = (max(c.shape[1] for c in part) + 3) // 4 * 4
            x = torch.ones(len(part), 1, H, W)
            for k, c in enumerate(part):
                x[k, 0, :, : c.shape[1]] = torch.from_numpy(c)
            widths = torch.tensor([c.shape[1] for c in part])
            logits = self.rec(((x - 0.5) / 0.5).to(self.device), widths).float()
            probs = logits.softmax(-1)
            texts = greedy(logits, self.charset, widths)
            logp = logits.log_softmax(-1).cpu() if self.lex else None
            for k, t in enumerate(texts):
                T = min(probs.shape[1], (int(widths[k]) + 3) // 4)
                mx = probs[k, :T].max(-1)
                keep = mx.indices != 0
                conf = float(mx.values[keep].mean()) if keep.any() else 0.0
                conf = round(conf, 3) if math.isfinite(conf) else 0.0
                raw = None
                if self.lex:
                    fixed, changed = self.lex.correct(t, conf, logp[k, :T])
                    if changed:
                        raw, t = t, fixed
                out.append((t, conf, raw))
        return out

    def read(self, data: bytes) -> dict:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        boxes = self.detect(img)
        words = [{"box": [int(round(float(v))) for v in b], "text": str(t), "conf": float(c), **({"raw": raw} if raw else {})}
                 for b, (t, c, raw) in zip(boxes, self.recognize(img, boxes)) if t]
        lines = group_lines(words)
        text = "\n".join(ln["text"] for ln in lines)
        return {"width": img.width, "height": img.height, "words": words, "lines": lines, "text": text,
                "ingredients": extract_ingredients(lines)}


def group_lines(words: list[dict]) -> list[dict]:
    """세로 중심이 가까운 단어끼리 한 줄로 묶고 줄 안에서는 왼쪽부터 놓는다."""
    if not words:
        return []
    hs = sorted(w["box"][3] - w["box"][1] for w in words)
    tol = 0.6 * hs[len(hs) // 2]
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["box"][1] + w["box"][3]) / 2):
        cy = (w["box"][1] + w["box"][3]) / 2
        if rows and abs(cy - rows[-1][-1]["_cy"]) <= tol:
            rows[-1].append({**w, "_cy": cy})
        else:
            rows.append([{**w, "_cy": cy}])
    lines = []
    for r in rows:
        r.sort(key=lambda w: w["box"][0])
        lines.append({"text": " ".join(w["text"] for w in r), "conf": round(sum(w["conf"] for w in r) / len(r), 3),
                      "box": [min(w["box"][0] for w in r), min(w["box"][1] for w in r),
                              max(w["box"][2] for w in r), max(w["box"][3] for w in r)]})
    return lines


def extract_ingredients(lines: list[dict]) -> list[str]:
    """'전성분' 다음부터 다음 항목 제목(사용법·주의사항 등) 전까지를 쉼표로 나눈다. 시작 문구가 없으면 빈 목록."""
    text = " ".join(ln["text"] for ln in lines)
    m = START.search(text)
    if not m:
        return []
    body = text[m.end():]
    stop = STOP.search(body)
    if stop:
        body = body[: stop.start()]
    parts = re.split(r"\s*[,，、]\s*", body)
    return [p.strip(" .·:;") for p in parts if len(p.strip(" .·:;")) >= 2]
