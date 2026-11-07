"""식약처 화장품 공공데이터 API(data.go.kr, 이용허락범위 제한 없음)를 받아 판정 엔진용 CSV로 만든다.

실행:
  python -m certcheck.mfds_api fetch <원본폴더>    # 인증키는 ~/.config/datagokr/key (화면·파일에 남기지 않음)
  python -m certcheck.mfds_api build <원본폴더>    # data/regs/성분규제_식약처API.csv, data/kr/*.csv 생성

- 화장품 사용제한 원료정보(15111772): 나라별 금지·한도 → 통합표에 없던 한국·아세안·브라질·아르헨티나·캐나다·미국 목록
- 화장품 원료성분정보(15111774): 한글 표준명·이명 ↔ 영문 INCI ↔ CAS 사전(한글 성분명 입력 변환)
- 화장품 규제정보(15111773): 성분별 금지·제한 국가 요약(참고용)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .data import DATA

SERVICES = {
    "ingredients": "CsmtcsIngdCpntInfoService01/getCsmtcsIngdCpntInfoService01",
    "use_restrict": "CsmtcsUseRstrcInfoService/getCsmtcsUseRstrcInfoService",
    "regulation": "CsmtcsReglMaterialInfoService/getCsmtcsReglMaterialInfoService",
}
# EU·일본은 통합표의 원문(EU CosIng CC BY 4.0, 일본 후생노동성 고시 — 출처 표기 조건 사용 가능)을 쓴다.
# 중국·대만 원문 목록(IECIC·안전기술규범 2015·TFDA 목록)은 운영진 데이터 검토(2026-11-07)에서 '사용 불가'라 이 API 행으로 대신한다.
COUNTRY = {"한국": "KR", "아세안": "ASEAN", "브라질": "BR", "아르헨티나": "AR", "캐나다": "CA", "미국": "US", "중국": "CN", "대만": "TW"}
REG_FIELDS = ["jurisdiction", "list_type", "name", "inci", "cas", "max_conc", "product_scope", "conditions", "source_file",
              "source_ref", "last_update"]
SOURCE = "식약처 화장품 사용제한 원료정보 API(data.go.kr 15111772)"
# 성분 자체의 배합 한도를 적은 구절만 한도로 읽는다(불순물·2급 아민 함량 같은 다른 수치는 조건으로만 둔다)
LIMIT_RE = re.compile(r"(?:배합한도(?:\s*\([^)]*\))?|Maximum (?:authorised |authorized )?concentration[^:：]*|최대 (?:허용 )?농도[^:：]*)\s*[:：]\s*([^*]+)", re.I)
SCOPE_RE = re.compile(r"(?:Product [Tt]ype[^:：]*|제품 유형[^:：]*)\s*[:：]\s*([^*]+)")
OTHER_QUANTITY = re.compile(r"amine|impurit|불순물|아민|nitrosamine|free formaldehyde", re.I)


def fetch(out: Path, rows: int = 500) -> None:
    key = (Path.home() / ".config/datagokr/key").read_text().strip()
    out.mkdir(parents=True, exist_ok=True)

    def call(path: str, page: int) -> dict:
        q = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": rows, "type": "json"})
        with urllib.request.urlopen(f"https://apis.data.go.kr/1471000/{path}?{q}", timeout=60) as r:
            return json.loads(r.read())

    for name, path in SERVICES.items():
        first = call(path, 1)
        total = first["body"]["totalCount"]
        items = list(first["body"].get("items") or [])
        for page in range(2, (total + rows - 1) // rows + 1):
            for _ in range(3):
                try:
                    items += list(call(path, page)["body"].get("items") or [])
                    break
                except OSError:
                    time.sleep(2)
            time.sleep(0.2)
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(it, ensure_ascii=False) + "\n" for it in items)
        print(name, total, len(items))


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("^", " ")).strip()


def restriction_rows(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        juris = COUNTRY.get(it.get("COUNTRY_NAME"))
        if not juris:
            continue
        cond = _clean(it.get("LIMIT_COND"))
        kind = it.get("REGULATE_TYPE") or ""
        list_type = "banned" if kind == "금지" else "restricted"
        if juris == "US" and kind == "한도" and "Eye Area" in cond:
            list_type = "allowed_colorant"  # 미국 색소 첨가물 허용 표(사용 부위별 가능 여부)
        limit = " / ".join(m.strip() for m in LIMIT_RE.findall(cond) if not OTHER_QUANTITY.search(m))[:240]
        inci, cas = _clean(it.get("INGR_ENG_NAME")), _clean(it.get("CAS_NO")).replace(" ", "")
        notice = (it.get("NOTICE_INGR_NAME") or "").lower()
        if "silver" in notice or "prata" in cond.lower() or "은(silver" in cond.lower():
            inci, cas = "Citric Acid (and) Silver Citrate", ""  # 혼합 보존제 항목 — 구성 성분(시트르산)으로 찾지 않게
        scope = " / ".join(m.strip() for m in SCOPE_RE.findall(cond))[:240]
        out.append({"jurisdiction": juris, "list_type": list_type, "name": _clean(it.get("NOTICE_INGR_NAME") or it.get("INGR_STD_NAME")),
                    "inci": inci, "cas": cas,
                    "max_conc": limit, "product_scope": scope,
                    "conditions": (("일부 용도 금지 · " if kind == "한도/금지" else "") + cond)[:600],
                    "source_file": SOURCE, "source_ref": f"{it.get('COUNTRY_NAME')} {_clean(it.get('PROVIS_ATRCL'))}".strip(),
                    "last_update": "2026-11-07 수집"})
    return out


def build(raw: Path) -> None:
    load = lambda n: [json.loads(line) for line in (raw / f"{n}.jsonl").open(encoding="utf-8")]  # noqa: E731
    regs = restriction_rows(load("use_restrict"))
    path = DATA / "regs" / "성분규제_식약처API.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=REG_FIELDS)
        w.writeheader()
        w.writerows(regs)
    print(path.name, len(regs))
    kr = DATA / "kr"
    kr.mkdir(exist_ok=True)
    ings = load("ingredients")
    with (kr / "식약처_원료성분사전.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["kr_name", "inci", "cas", "synonyms"])
        for it in ings:
            w.writerow([_clean(it.get("INGR_KOR_NAME")), _clean(it.get("INGR_ENG_NAME")), _clean(it.get("CAS_NO")), _clean(it.get("INGR_SYNONYM"))])
    print("식약처_원료성분사전.csv", len(ings))
    with (kr / "식약처_국가별규제요약.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["kr_name", "inci", "banned_in", "restricted_in"])
        for it in load("regulation"):
            w.writerow([_clean(it.get("INGR_STD_NAME")), _clean(it.get("INGR_ENG_NAME")), _clean(it.get("PROH_NATIONAL")), _clean(it.get("LIMIT_NATIONAL"))])
    print("식약처_국가별규제요약.csv")


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1]](Path(sys.argv[2]))
