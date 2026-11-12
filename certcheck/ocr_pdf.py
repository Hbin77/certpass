"""PDF 전성분표 읽기: 글자 정보가 있는 쪽은 그대로 꺼내고, 이미지뿐인 쪽(스캔·가림 처리본)은 그림으로 바꿔 OCR 서빙에 보낸다.

- 앞에서부터 최대 PDF_MAX_PAGES쪽. 전체 시간 예산(PDF_BUDGET초)을 넘기면 거기까지만 읽는다(화면은 접수 → 결과 조회라 60초 프록시와 무관)
- 이미지 쪽은 화면(web/app.js)과 같은 규칙으로 다시 읽는다: 사전과 정확히 맞은 성분이 3종 미만이면 90°·270°,
  글자 줄 기울기가 1° 이상이면 바로 세워 한 번 더(남으면 0.5° 이상에서 한 번 더). 결과가 나빠지면 앞 결과를 쓴다
- PDF는 PDFium(pypdfium2)으로 연다. 쪽 수·그림 크기에 상한을 두고, 글자 정보는 읽기만 한다(스크립트·첨부는 쓰지 않음)
"""
from __future__ import annotations

import io
import os
import re
import time

from . import ocr_client as oc

PDF_MAGIC = b"%PDF-"
LONG_SIDE = 2400  # 화면이 사진을 줄이는 크기와 같게
MAX_SCALE = 4.0  # 아주 작은 쪽을 지나치게 키우지 않게
TEXT_MIN_LETTERS = 20  # 이보다 글자가 적으면 이미지 쪽으로 본다
LETTER = re.compile(r"[A-Za-z가-힣]")
# 전성분 구역(ocr/pipeline.py의 START·STOP·extract_ingredients와 같은 규칙. 앱은 torch 없이 돌아야 해서 따로 둔다)
START = re.compile(r"(전\s*성\s*분|INGREDIENTS?|Ingredients?)\s*[:：]?")
STOP = re.compile(r"(사용\s*(방법|법|시의|상의)|주의\s*사항|용\s*량|내\s*용\s*량|제조\s*(업자|번호|국)|책임\s*판매|품질\s*보증|"
                  r"사용\s*기한|개봉\s*후|How to use|Caution|Directions|Made in)", re.I)


class PdfError(ValueError):
    """열 수 없는 PDF(암호·손상). 화면에는 422로 알린다."""


def max_pages() -> int:
    return int(os.environ.get("CERTCHECK_PDF_MAX_PAGES", "4"))


def budget() -> float:
    """화면은 접수 → 결과 조회(ocr_jobs)라 공개 프록시 60초에 묶이지 않는다. 서빙이 붐빌 때도 4쪽을 읽게 90초."""
    return float(os.environ.get("CERTCHECK_PDF_BUDGET", "90"))


def extract_section(lines: list[str]) -> list[str]:
    text = " ".join(lines)
    m = START.search(text)
    if not m:
        return []
    body = text[m.end():]
    stop = STOP.search(body)
    if stop:
        body = body[: stop.start()]
    return [p.strip(" .·:;") for p in re.split(r"\s*[,，、]\s*", body) if len(p.strip(" .·:;")) >= 2]


def _exact(res: dict) -> int:
    texts = [ln.get("text", "") for ln in res.get("lines") or []]
    items, _ = oc.choose(oc.match_all(res.get("ingredients") or [], "\n".join(texts)), texts)
    return sum(i["match"] == "exact" for i in items)


def _jpeg(img, deg: float) -> bytes:
    if deg:
        img = img.rotate(-deg, expand=True, fillcolor=255)  # 화면 캔버스와 같이 양수 = 시계 방향
    s = min(1.0, LONG_SIDE / max(img.size))
    if s < 1:
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=90)
    return b.getvalue()


def _ocr_page(img, deadline: float) -> tuple[dict | None, float, int]:
    """이미지 쪽 하나 → (가장 나은 서빙 응답, 돌린 각도, 호출 수). 시간이 다 되면 그때까지의 결과."""
    best, best_n, angle, calls = None, -1, 0.0, 0

    def try_(deg: float, tie: bool = True) -> bool:
        """tie: 정확 일치 수가 같아도 새 결과를 쓴다(기울기 보정은 같으면 바로 세운 쪽, 90° 돌리기는 더 많을 때만)."""
        nonlocal best, best_n, angle, calls
        if best is not None and time.monotonic() > deadline:
            return False
        res = oc.call_ocr(_jpeg(img, deg), "image/jpeg")
        calls += 1
        n = _exact(res)
        if n > best_n or (tie and n == best_n):
            best, best_n, angle = res, n, deg
            return True
        return False

    for deg in (0, 90, 270):
        try_(deg, tie=False)
        if best_n >= 3 or time.monotonic() > deadline:
            break
    for lim in (1.0, 0.5):  # 기울기 보정(화면과 같은 규칙)
        skew = oc.estimate_skew((best or {}).get("words") or [])
        if skew is None or not lim <= abs(skew) <= 20 or not try_(angle - skew):
            break
    return best, angle, calls


def read_pdf(data: bytes) -> dict:
    import pypdfium2 as pdfium  # PDF를 받을 때만 읽는다

    t0 = time.monotonic()
    deadline = t0 + budget()
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise PdfError(str(e)) from e
    try:
        total = len(pdf)
        pages, lines, section, words, model = [], [], [], [], None
        for i in range(min(total, max_pages())):
            if i and time.monotonic() > deadline:
                break
            page = pdf[i]
            try:
                tp = page.get_textpage()
                text = tp.get_text_range() or ""
                tp.close()
                if len(LETTER.findall(text)) >= TEXT_MIN_LETTERS:
                    pl = [ln.strip() for ln in text.splitlines() if ln.strip()]
                    lines += pl
                    section += extract_section(pl)
                    pages.append({"page": i + 1, "source": "text"})
                    continue
                w, h = page.get_size()
                scale = min(MAX_SCALE, LONG_SIDE / max(1.0, w, h))
                img = page.render(scale=scale, grayscale=True).to_pil().convert("L")
            finally:
                page.close()
            res, angle, calls = _ocr_page(img, deadline)
            if res is None:
                break
            model = res.get("model") or model
            lines += [ln.get("text", "") for ln in res.get("lines") or []]
            sec, _, _ = oc.best_section(res)  # 전개도처럼 판넬이 여럿이면 전성분 판넬만 다시 묶는다
            section += sec
            words += res.get("words") or []
            pages.append({"page": i + 1, "source": "ocr", "angle": round(angle, 1), "calls": calls})
    finally:
        pdf.close()
    items, method = oc.choose(oc.match_all(section, "\n".join(lines)), lines)
    read = len(pages)
    return {
        "ingredients": items,
        "found_section": bool(items),
        "method": method,
        "text": "\n".join(lines)[:20000],
        "lines": [{"text": t, "conf": None} for t in lines][:400],
        "words": len(words) or sum(len(t.split()) for t in lines),
        "model": model,
        "counts": {k: sum(i["match"] == k for i in items) for k in ("exact", "fuzzy", "unknown")},
        "label": oc.label_info(lines, names=method == "section"),
        "skew": None,  # 쪽마다 서버에서 이미 바로 세웠다(화면이 다시 돌리지 않게)
        "quality": oc.photo_quality(words) if words else {"low_conf_share": None, "text_px": None, "blurry": False},
        "pdf": {"pages_total": total, "pages_read": read, "pages": pages,
                "partial": read < min(total, max_pages()) or total > max_pages(), "sec": round(time.monotonic() - t0, 1)},
    }
