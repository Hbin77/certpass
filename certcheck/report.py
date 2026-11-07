"""판정 결과를 표(CSV), 상세(JSON), 보고서(Markdown)로 내보낸다."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import STATUS_COND, STATUS_FAIL, STATUS_NA, STATUS_PASS
from .classify import Verdict

ICON = {STATUS_PASS: "통과", STATUS_COND: "조건부", STATUS_FAIL: "불가", STATUS_NA: "-"}


def write_all(verdicts: list[Verdict], out_dir: Path, title: str = "인증 사전 적합성 판정") -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"matrix": out_dir / "matrix.csv", "detail": out_dir / "detail.json", "report": out_dir / "report.md",
             "features": out_dir / "features.csv"}
    products = sorted({(v.product_id, v.product_name) for v in verdicts})
    certs = sorted({(v.cert_id, v.cert_name, v.jurisdiction, v.kind) for v in verdicts})
    cell = {(v.product_id, v.cert_id): v for v in verdicts}

    with paths["matrix"].open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cert_id", "인증·등록", "관할", "종류"] + [f"{pid} {pn}" for pid, pn in products])
        for cid, cn, j, k in certs:
            w.writerow([cid, cn, j, k] + [cell[(pid, cid)].status if (pid, cid) in cell else "" for pid, _ in products])

    paths["detail"].write_text(json.dumps([v.to_dict() for v in verdicts], ensure_ascii=False, indent=1), encoding="utf-8")

    rows = [dict(product_id=v.product_id, cert_id=v.cert_id, status=v.status, **v.features) for v in verdicts if v.features]
    if rows:
        with paths["features"].open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    lines = [f"# {title}", "",
             "등급: **불가**=재처방해야 통과 / **조건부**=재처방 없이 서류·현지책임자·문구·시험 보완으로 통과 / "
             "**통과 가능**=현재 상태로 통과 / **해당 없음**=적용 대상 아님. 모든 판정은 예비 판정이며 근거를 함께 적었다.", ""]
    for pid, pn in products:
        vs = [v for v in verdicts if v.product_id == pid]
        c = Counter(v.status for v in vs)
        lines += [f"## {pid} {pn}", "",
                  f"통과 가능 {c[STATUS_PASS]} · 조건부 {c[STATUS_COND]} · 불가 {c[STATUS_FAIL]} · 해당 없음 {c[STATUS_NA]}", "",
                  "| 인증·등록 | 관할 | 판정 | 핵심 사유 | 해야 할 일 |", "|---|---|---|---|---|"]
        for v in vs:
            if v.status == STATUS_NA:
                continue
            key = [f for f in v.findings if f.level == ("fail" if v.status == STATUS_FAIL else "cond")][:3]
            reason = "<br>".join(f.message for f in key) or "-"
            acts = "<br>".join(sorted({f.action for f in key if f.action})) or "-"
            lines.append(f"| {v.cert_name} | {v.jurisdiction} | **{v.status}** | {reason} | {acts} |")
        na = [v.cert_name for v in vs if v.status == STATUS_NA]
        if na:
            lines += ["", f"해당 없음({len(na)}): " + ", ".join(na)]
        lines.append("")
    # 제품 공통 과제: 여러 인증에 반복되는 조치
    acts = defaultdict(set)
    for v in verdicts:
        for f in v.findings:
            if f.level in ("fail", "cond") and f.action:
                acts[f.action].add(v.cert_id)
    if acts:
        lines += ["## 여러 인증에 반복되는 조치 (먼저 하면 효율 큼)", "", "| 조치 | 관련 인증 수 |", "|---|---|"]
        for a, s in sorted(acts.items(), key=lambda x: -len(x[1]))[:15]:
            lines.append(f"| {a} | {len(s)} |")
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
