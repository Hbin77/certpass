"""데이터 적재: 제품, 인증 요건 카드, 성분 규제 통합표, 성분 속성표."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .normalize import norm_inci, split_cas

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@dataclass
class RegRow:
    jurisdiction: str
    list_type: str          # banned / restricted / allowed_preservative / allowed_uv / allowed_colorant / inventory
    name: str
    inci: str
    cas: list[str]
    max_conc: str
    product_scope: str
    conditions: str
    source_ref: str
    source_file: str
    last_update: str
    key: str = ""


# 한 행에 여러 성분이 묶인 표기('Retinol; Retinyl Acetate | RETINOL,RETINYL ACETATE')를 나눈다.
# '|'·';'는 항상 목록 구분자. 쉼표는 뒤에 공백이 없을 때만 목록 구분자(CosIng 'RETINOL,RETINYL ACETATE')로 보고,
# 'Citric acid, ammonium nickel salt'·'CITRUS PARADISI, X C. RETICULATA'처럼 쉼표+공백은 이름의 일부로 둔다.
# 숫자 사이 쉼표(1,2-Hexanediol)와 '/'는 나누지 않는다.
_LIST_SEP = re.compile(r"\s*[|;]\s*")
_COMMA_SEP = re.compile(r"(?<!\d),(?![\d\s])")
_NAME_HEAD = re.compile(r",?\s+(?:with the exception|except|excluding|other than)\b", re.I)


def is_blend(r: "RegRow") -> bool:
    return "(and)" in (r.inci or "").lower()


def _usable(k: str) -> bool:
    return len(k) >= 3 and any(ch.isalpha() for ch in k)


def row_keys(r: "RegRow") -> set[str]:
    """색인 키: 전체 표기 + 목록으로 묶인 성분 토큰 + 이름의 예외 문구 앞부분. 혼합 원료 행은 혼합 표기 자체만."""
    if is_blend(r):
        return {norm_inci((r.inci or "").split("|")[0])} - {""}
    keys = {norm_inci(r.inci), norm_inci(r.name)}
    head_part, _, inci_list = (r.inci or "").partition("|")
    for chunk in _LIST_SEP.split(head_part):
        k = norm_inci(chunk)
        if _usable(k):
            keys.add(k)
        keys |= {x for x in (norm_inci(y) for y in _COMMA_SEP.split(chunk) if y.strip()) if _usable(x)}
    for chunk in _LIST_SEP.split(inci_list):  # CosIng 형식('화학명 | INCI,INCI,…')의 '|' 뒤 INCI 목록
        keys |= {x for x in (norm_inci(y) for y in _COMMA_SEP.split(chunk) if y.strip()) if _usable(x)}
    head = norm_inci(_NAME_HEAD.split(r.name or "", 1)[0])
    if _usable(head):
        keys.add(head)
    return keys - {""}


@dataclass
class RegIndex:
    """관할별로 INCI 키와 CAS로 빠르게 찾는 색인."""
    by_key: dict[tuple[str, str], list[RegRow]] = field(default_factory=dict)
    by_cas: dict[tuple[str, str], list[RegRow]] = field(default_factory=dict)
    jurisdictions: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=dict)
    has_inci: dict[str, bool] = field(default_factory=dict)

    def add(self, r: RegRow) -> None:
        self.jurisdictions.add(r.jurisdiction)
        if r.inci or r.cas:
            self.has_inci[r.jurisdiction] = True
        self.counts[f"{r.jurisdiction}:{r.list_type}"] = self.counts.get(f"{r.jurisdiction}:{r.list_type}", 0) + 1
        for k in row_keys(r):
            self.by_key.setdefault((r.jurisdiction, k), []).append(r)
        if is_blend(r):  # 'Citric Acid (and) Silver Citrate' 같은 혼합 원료 행은 구성 성분 CAS로 찾지 않는다
            return
        for c in r.cas:
            self.by_cas.setdefault((r.jurisdiction, c), []).append(r)

    def lookup(self, jurisdiction: str, inci: str, cas: list[str]) -> list[tuple[RegRow, str]]:
        hits: dict[int, tuple[RegRow, str]] = {}
        for c in cas:
            for r in self.by_cas.get((jurisdiction, c), []):
                hits[id(r)] = (r, "cas")
        k = norm_inci(inci)
        for r in self.by_key.get((jurisdiction, k), []):
            hits.setdefault(id(r), (r, "inci_exact"))
        return list(hits.values())


def load_products(path: Path | None = None) -> dict:
    path = path or DATA / "private" / "products" / "products.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_cards(folder: Path | None = None) -> list[dict]:
    folder = folder or DATA / "certs"
    cards = []
    for p in sorted(folder.glob("*.yaml")):
        try:
            c = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:  # 카드 한 장 오류로 전체가 멈추지 않게 한다
            print(f"[경고] 카드 파싱 실패 {p.name}: {e}")
            continue
        if isinstance(c, dict) and c.get("id"):
            c["_file"] = p.name
            cards.append(c)
    return cards


MFDS_REGS = DATA / "regs" / "성분규제_식약처API.csv"  # 식약처 API로 받은 한국·아세안·브라질·아르헨티나·캐나다·미국 목록


def load_reg_index(path: Path | None = None, extra: list[Path] | None = None) -> RegIndex:
    if path is None:
        jp = DATA / "regs" / "성분규제_통합표_JP보강.csv"
        path = jp if jp.exists() else DATA / "regs" / "성분규제_통합표.csv"
        extra = [MFDS_REGS] if extra is None and MFDS_REGS.exists() else extra
    idx = RegIndex()
    for one in [path, *(extra or [])]:
        if one.exists():
            _load_reg_file(idx, one)
    return idx


def _load_reg_file(idx: RegIndex, path: Path) -> None:
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            idx.add(RegRow(
                jurisdiction=(row.get("jurisdiction") or "").strip().upper(),
                list_type=(row.get("list_type") or "").strip(),
                name=row.get("name") or "",
                inci=row.get("inci") or "",
                cas=split_cas(row.get("cas")),
                max_conc=row.get("max_conc") or "",
                product_scope=row.get("product_scope") or "",
                conditions=row.get("conditions") or "",
                source_ref=row.get("source_ref") or "",
                source_file=row.get("source_file") or "",
                last_update=row.get("last_update") or "",
            ))


def load_attributes(path: Path | None = None) -> dict[str, dict]:
    path = path or DATA / "ingredients" / "ingredient_attributes.csv"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = norm_inci(row.get("inci"))
            if k:
                out[k] = row
    return out


KR_DICT = DATA / "kr" / "식약처_원료성분사전.csv"


def kr_key(name: str | None) -> str:
    """한글 성분명 비교 키: 띄어쓰기·가운뎃점·쉼표·빗금·괄호·하이픈 차이는 무시('1,2-헥산다이올' = '12헥산다이올')."""
    return re.sub(r"[\s·ㆍ,/()\[\]\-*]", "", (name or "")).lower()


def load_kr_dict(path: Path | None = None) -> dict[str, dict]:
    """식약처 화장품 원료성분정보: 한글 표준명·이명 → {inci, cas, kr_name}. 영문명이 없는 행은 뺀다."""
    path = path or KR_DICT
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("inci"):
                continue
            hit = {"inci": re.split(r",(?!\s)", row["inci"])[0].strip(), "cas": row.get("cas") or None, "kr_name": row["kr_name"]}
            out.setdefault(kr_key(row["kr_name"]), hit)
            for syn in re.split(r"[,;]", row.get("synonyms") or ""):
                if syn.strip():
                    out.setdefault(kr_key(syn), hit)
    return out
