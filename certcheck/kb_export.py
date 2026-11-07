"""AgentStream 지식베이스(RAG 문서)용으로 인증 요건 카드를 문서로 바꾼다.

실행: .venv/bin/python -m certcheck.kb_export [출력폴더=out/agentstream_kb]
- 카드 1장 → 문서 1개(카드ID.md). AgentStream은 파일마다 '처리 시작 → 파싱 결과 승인'을 눌러야 해서,
  올릴 때는 묶음 폴더(출력폴더_묶음/)의 파일(지역·종류별 카드 묶음을 파일당 38KB 이하로 자동 분할 + 공통 판정기준)을 쓴다.
  285KB 한 파일은 AgentStream 문서 분석 단계에서 DATAPROCESSOREXCEPTION으로 실패했다(34KB도 동시 처리 때 실패 → 둘로 나눠 올림).
  AgentStream은 절 경계와 상관없이 일정 길이로 조각을 자르므로, 어느 인증 이야기인지 알도록 모든 줄 머리에 [EUCPNP] 꼬리표
  (지식베이스 변환이 밑줄을 지워 저장하는 모양)를 붙인다.
- 공개 링크(http·https)만 싣는다. 로컬 원문 경로(local:)·원문 인용(quote)·엔진 태그([kw:…])는 뺀다
  (인증기관 기준 원문은 게재하지 않고 링크로만 안내하는 화면 규칙과 같다).
- data/private(자사 실데이터)는 읽지 않는다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .data import DATA, load_cards

KW = re.compile(r"\s*\[kw:[^\]]*\]")
KIND = {"mandatory_registration": "국가 의무 등록·신고", "voluntary_certification": "민간 자율 인증",
        "marketing_label": "마케팅 표시 인증", "packaging": "포장 규제", "company_certification": "기업 인증",
        "chemical_registration": "화학물질 등록·규제", "mandatory_compliance": "의무 준수 규제"}
LEVEL = {"direct": "원문 확인", "secondary": "2차 자료", "unverified": "미확인(주소만)"}
EFFECT = {"ok": "가능", "drug_risk": "의약품 오인 위험", "not_allowed": "불가", "conditional": "조건부"}


def _t(s) -> str:
    return KW.sub("", str(s)).strip()


def kb_tag(card_id: str) -> str:
    """지식베이스 꼬리표. AgentStream은 제목의 밑줄을 지우므로(EU_CPNP → EUCPNP) 처음부터 밑줄 없이 쓴다(llm_client.kb_tag와 같음)."""
    return re.sub(r"[^A-Z0-9]", "", str(card_id).upper())


SENT = re.compile(r"(?<=[.。;])\s+")


def card_doc(c: dict) -> str:
    """AgentStream은 절 경계와 상관없이 일정 길이로 조각을 자른다(2026-11-07 실측: '# 기간·비용·유' 같은 조각).
    어느 조각에도 어느 카드인지 남도록 모든 줄 머리에 [꼬리표]를 붙이고, 긴 메모는 문장마다 나눈다."""
    k = kb_tag(c["id"])
    tag = f"[{k} {c.get('name_ko', '')}]"
    t = f"[{k}]"
    out = [f"# {c.get('name_ko', '')} ({c['id']})", "",
           f"{tag} 영문명: {c.get('name_en') or '-'} / 관할: {c.get('jurisdiction') or '-'} / "
           f"종류: {KIND.get(c.get('kind'), c.get('kind'))} / 성분 규제 목록: {c.get('ingredient_rules') or '없음'}"]

    def sec(title: str, lines: list[str]) -> None:
        lines = [x for x in lines if x]
        if lines:
            out.extend(["", f"## {title} {tag}", *[f"- {t} {x[2:] if x.startswith('- ') else x}" for x in lines]])

    ap = c.get("applies_to") or {}
    sec("적용 대상", [f"- 제품 유형: {', '.join(ap.get('product_types') or []) or '-'}",
                   f"- 조건: {_t(ap['condition'])}" if ap.get("condition") else ""])
    sec("불가 조건(재처방해야 통과)", [f"- {_t(r)}" for r in c.get("blocking_rules") or []])
    sec("조건부 조건(서류·시험·책임자 등 보완으로 통과)", [f"- {_t(r)}" for r in c.get("conditional_rules") or []])
    sec("표방 문구 규칙", [f"- {r.get('claim')}: {EFFECT.get(r.get('effect'), r.get('effect'))} — {_t(r.get('note') or '')}"
                       for r in c.get("claim_rules") or [] if isinstance(r, dict)])
    le = c.get("local_entity") or {}
    sec("현지 책임자", [f"- 필요: {'예' if le.get('required') else '아니오'}" + (f" — {_t(le['role'])}" if le.get("role") else "")])
    sec("필요 서류", [f"- {d.get('id')}: {_t(d.get('desc') or '')} (작성 주체: {d.get('producer') or '-'})"
                   for d in c.get("documents_required") or [] if isinstance(d, dict)])
    sec("필요 시험", [f"- {', '.join(map(str, c.get('tests_required') or []))}" if c.get("tests_required") else ""])
    lb = c.get("labeling") or {}
    sec("표시(라벨)", [f"- 언어: {_t(lb['language'])}" if lb.get("language") else "",
                     f"- 알레르기 성분: {_t(lb['allergens'])}" if lb.get("allergens") else "",
                     *[f"- {_t(x)}" for x in lb.get("other") or []]])
    sec("동물실험", [f"- {c['animal_testing']}" if c.get("animal_testing") else ""])
    tl = c.get("timeline") or {}
    sec("기간·비용·유효기간", [f"- {k}: {_t(tl[k])}" for k in ("lead_time", "fee", "validity") if tl.get(k)])
    sec("참고 메모", [x for x in SENT.split(_t(c["notes"])) if x.strip()] if c.get("notes") else [])
    seen, ev = set(), []
    for e in c.get("evidence") or []:
        url = str((e or {}).get("url", ""))
        if url.startswith(("https://", "http://")) and url not in seen:
            seen.add(url)
            title = e.get("title") if e.get("title") and e.get("title") != url else None
            ev.append(f"- {title + ' — ' if title else ''}{url} ({LEVEL.get(e.get('level'), e.get('level') or '-')})")
    sec("근거 문서(출처 링크)", ev)
    out.extend(["", f"- {t} 표기 규칙: '(추정)'은 일반 지식으로 채운 부분, '(2차)'는 2차 자료로만 확인한 부분이다. "
                    "이 문서는 공개 기준을 정리한 참고 자료이며 인증기관의 공식 심사가 아니다.", ""])
    return "\n".join(out)


GUIDE = """# CertPass 판정 기준 안내(공통)

## 판정 등급 정의 [CertPass 공통]
- 불가: 재처방(포장재 변경 포함)해야만 통과할 수 있다.
- 조건부: 서류·현지 책임자·표방 문구·시험·원료 증명·미확인 데이터를 보완하면 통과할 수 있다.
- 통과 가능: 현재 처방·서류로 요건을 충족한다.
- 해당 없음: 제품 유형·표방 문구가 이 인증의 적용 대상이 아니다.
- 판정 등급은 CertPass 규칙 엔진이 정한다. 설명(AI)은 등급을 바꾸지 않고 근거를 풀어 쓴다.

## 판정에 쓰는 자료 [CertPass 공통]
- 인증 요건 카드 56장: 인증·등록 1개당 문서 1개(적용 대상, 불가·조건부 조건, 서류, 시험, 표시, 근거 링크).
- 성분 규제 목록: EU 화장품규정 부속서 II~VI(European Commission CosIng, CC BY 4.0, 판정용으로 가공),
  일본 화장품기준(후생노동성 고시 제331호) 별표(판정용으로 가공), 식품의약품안전처 화장품 사용제한 원료정보
  (공공데이터포털 15111772 — 한국·아세안·중국·대만·브라질·아르헨티나·캐나다·미국).
- 중국 已使用化妆品原料目录(IECIC) 등재 여부는 원문 목록을 쓰지 않으므로 '확인 필요'로만 안내한다.
- 민간 인증(비건·천연·유기농·할랄 등)은 공개 사실을 자체 문장으로 요약하고 원문 링크만 둔다. 기준서 원문·표는 싣지 않는다.
- 판정 결과의 '근거' 문구(예: 'REACH 부속서 XVII 70항', '부속서 II ref 1388')는 위 목록의 해당 항목을 가리킨다.

## 표기 규칙 [CertPass 공통]
- (추정): 원문으로 확인하지 못하고 일반 지식으로 채운 부분. 단정하지 말고 원문 확인을 권한다.
- (2차): 컨설팅·KOTRA·언론 등 2차 자료로만 확인한 부분.
- 근거 수준 '원문 확인' / '2차 자료' / '미확인(주소만)'은 근거 문서 링크의 신뢰 수준이다.
- 이 자료는 예비 점검용이며 공식 인증·심사가 아니다. 최종 판단은 각 기관과 자격 있는 안전성 평가자가 한다.
"""


MAX_FILE = 38_000  # 바이트. 39KB 파일은 처리됐고 285KB는 실패(2026-11-07)
GROUPS = [  # (파일 이름, 카드 id 앞부분·id). 어디에도 안 맞는 카드는 마지막 '기타'로 간다
    ("유럽_영국_유라시아", ("EU_", "UK_", "EAEU_")),
    ("동아시아_중국_일본_대만", ("CN_", "JP_", "TW_")),
    ("아세안1_말레이시아_인도네시아_태국_필리핀", ("MY_", "ID_", "TH_", "PH_")),
    ("아세안2_베트남_싱가포르_캄보디아_미얀마_인도", ("VN_", "SG_", "KH_", "MM_", "IN_")),
    ("미주_미국_캐나다_중남미", ("US_", "CA_", "BR_", "AR_", "CO_", "PE_", "MX_")),
    ("중동_아프리카_오세아니아", ("SA_", "UAE_", "EG_", "MA_", "IR_", "AU_", "NZ_")),
    ("민간인증1_비건_동물실험_할랄_코셔", ("VEGAN_", "V_LABEL", "LEAPING_BUNNY", "HALAL", "KOSHER")),
    ("민간인증2_천연_유기농_피부", ("NATRUE", "NATURAL_", "USDA_", "RSPO", "ECARF", "DERMATEST")),
    ("한국_국내인증_기업인증", ("KR_",)),
]


def export(folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.md"):
        old.unlink()
    cards = load_cards(DATA / "certs")
    for c in cards:
        (folder / f"{c['id']}.md").write_text(card_doc(c), encoding="utf-8")
    (folder / "_CertPass_판정기준_안내.md").write_text(GUIDE, encoding="utf-8")
    bundle = folder.with_name(folder.name + "_묶음")
    bundle.mkdir(parents=True, exist_ok=True)
    for old in bundle.glob("*.md"):
        old.unlink()
    left = list(cards)
    for n, (name, keys) in enumerate(GROUPS + [("기타", ("",))], 1):
        part = [c for c in left if c["id"].startswith(keys)]
        left = [c for c in left if c not in part]
        packs, cur = [], []
        for c in part:  # 파일 하나가 MAX_FILE을 넘지 않게(285KB 한 파일은 AgentStream 문서 분석에서 실패)
            if cur and len("\n\n".join(card_doc(x) for x in cur + [c]).encode()) > MAX_FILE:
                packs.append(cur)
                cur = []
            cur.append(c)
        if cur:
            packs.append(cur)
        for j, pack in enumerate(packs, 1):
            suffix = f"_{j}" if len(packs) > 1 else ""
            head = (f"# CertPass 인증 요건 카드 — {name.replace('_', ' ')}{suffix} ({len(pack)}종)\n\n"
                    "공개 사실을 자체 문장으로 정리한 참고 자료이며 인증기관의 공식 심사가 아니다.\n\n")
            (bundle / f"CertPass_카드{n:02d}{suffix}_{name}.md").write_text(
                head + "\n\n".join(card_doc(c) for c in pack), encoding="utf-8")
    (bundle / "CertPass_판정기준_안내.md").write_text(GUIDE, encoding="utf-8")
    return len(cards) + 1


if __name__ == "__main__":
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/agentstream_kb")
    print(f"{export(dest)}개 문서 → {dest}")
