"""AIStream에 서빙한 판정 모델(표 분류)을 부른다. 설정이 없으면 규칙 판정만 쓴다.

환경변수 (서버 설정으로만 받음, 사용자 입력으로 주소를 바꾸지 않음)
- AISTREAM_URL: 서빙 엔드포인트 전체 주소. 없으면 ML 판정 생략
- AISTREAM_FORMAT: mlflow(기본, {"dataframe_split": ...}) | records({"instances": [{열: 값}]}) | csv
  | image(AIStream CNN 이미지 서빙 /infer: 행마다 28×28 PNG, multipart 필드 AISTREAM_IMAGE_FIELD 기본 file)
- AISTREAM_CLASSES: 확률 벡터로 답할 때 클래스 순서(기본 COND,FAIL,NOT_APPLICABLE,PASS = 사전순)
- AISTREAM_FAIL_THRESHOLD: 숨은 불가 경보 기준(모델의 불가 확률, 기본 0.3). 서빙 후 calibrate_aistream으로 test.csv를 돌려 다시 정한다
- AISTREAM_TIMEOUT: 초(기본 8)
열 순서는 학습 CSV와 같은 data/ml/feature_columns.json(export_aistream이 저장)을 쓴다.
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import STATUS_COND, STATUS_FAIL, STATUS_NA, STATUS_PASS
from .classify import PROXY, Verdict
from .data import DATA, RegIndex
from .risk import risk_features

CODE = {STATUS_PASS: "PASS", STATUS_COND: "COND", STATUS_FAIL: "FAIL", STATUS_NA: "NOT_APPLICABLE"}
STATUS = {v: k for k, v in CODE.items()}
COLUMNS_FILE = DATA / "ml" / "feature_columns.json"


def columns() -> list[str]:
    return json.loads(COLUMNS_FILE.read_text(encoding="utf-8"))


def feature_rows(verdicts: list[Verdict], cards_by_id: dict, product: dict, reg: RegIndex, cols: list[str]) -> list[list]:
    """학습 데이터(synth.build_dataset → export_aistream)와 같은 방식으로 특징 행을 만든다."""
    cache: dict[str, dict] = {}
    rows = []
    for v in verdicts:
        rules = ((cards_by_id.get(v.cert_id) or {}).get("ingredient_rules") or "none").upper()
        juris = PROXY.get(rules, rules)
        if juris not in cache:
            cache[juris] = risk_features(product, reg, juris)  # 목록이 없는 관할은 유사도 특징만 0
        row = {f"f_{k}": val for k, val in (v.features or {}).items()}
        row.update({f"r_{k}": val for k, val in cache[juris].items()})
        row[f"cert_{v.cert_id}"] = 1
        row[f"rule_{CODE[v.status]}"] = 1
        rows.append([row.get(c, 0) for c in cols])
    return rows


def _payload(cols: list[str], rows: list[list], fmt: str) -> tuple[bytes, str]:
    if fmt == "records":
        return json.dumps({"instances": [dict(zip(cols, r)) for r in rows]}).encode(), "application/json"
    if fmt == "csv":
        lines = [",".join(cols)] + [",".join(str(x) for x in r) for r in rows]
        return "\n".join(lines).encode(), "text/csv"
    return json.dumps({"dataframe_split": {"columns": cols, "data": rows}}).encode(), "application/json"


def parse_predictions(body: bytes | str, n: int, classes: list[str]) -> list[dict]:
    data = json.loads(body)
    if isinstance(data, dict):
        data = next((data[k] for k in ("predictions", "prediction", "outputs", "results") if k in data), data)
    out = []
    for pr in data:
        label, probs = None, None
        if isinstance(pr, dict):
            label = pr.get("label") or pr.get("prediction") or pr.get("class")
            probs = pr.get("probabilities") or pr.get("proba")
            if probs is None and any(k.startswith("proba_") for k in pr):  # aistream_train.py 서빙 형식
                probs = [float(pr.get(f"proba_{c}", 0.0)) for c in classes]
        elif isinstance(pr, list):
            probs = pr
        else:
            label = pr
        if probs and label is None:
            label = classes[max(range(len(probs)), key=probs.__getitem__)]
        label = str(label)
        if label.isdigit():
            label = classes[int(label)]
        if probs and len(probs) != len(classes):
            raise ValueError(f"확률 {len(probs)}개, 클래스 {len(classes)}개 — AISTREAM_CLASSES 확인")
        out.append({"label": label, "status": STATUS.get(label, label),
                    "proba": dict(zip(classes, probs)) if probs else None})
    if len(out) != n:
        raise ValueError(f"응답 {len(out)}건, 요청 {n}건")
    return out


def _multipart(field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "certpass" + os.urandom(8).hex()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def parse_image_response(body: bytes | str, classes: list[str]) -> dict:
    """AIStream CNN 서빙(/infer) 응답 한 건 → {label, status, proba}. 키 이름이 달라도 흔한 형태를 받아들인다."""
    d = json.loads(body)
    d = d.get("result") or d.get("prediction") if isinstance(d.get("result") or d.get("prediction"), dict) else d
    label = d.get("predicted_class") or d.get("class_name") or d.get("label") or d.get("class") or d.get("prediction")
    probs = d.get("probabilities") or d.get("class_probabilities") or d.get("probs") or d.get("scores")
    proba = None
    if isinstance(probs, dict):
        proba = {c: float(probs.get(c, 0.0)) for c in classes}
    elif isinstance(probs, list) and probs and isinstance(probs[0], dict):
        proba = {c: 0.0 for c in classes}
        for it in probs:
            name = it.get("class") or it.get("label") or it.get("class_name")
            if name in proba:
                proba[name] = float(it.get("probability", it.get("prob", it.get("score", 0.0))))
    elif isinstance(probs, list) and len(probs) == len(classes):
        proba = dict(zip(classes, map(float, probs)))
    if label is None and proba:
        label = max(proba, key=proba.get)
    label = str(label)
    if label.isdigit():
        label = classes[int(label)]
    return {"label": label, "status": STATUS.get(label, label), "proba": proba}


def call_model(url: str, cols: list[str], rows: list[list], classes: list[str], fmt: str, timeout: float) -> list[dict]:
    """서빙 모델 호출. fmt=image면 행마다 28×28 PNG(이미지 분류 템플릿용), 그 밖에는 한 번에 표 데이터."""
    if fmt != "image":
        body, ctype = _payload(cols, rows, fmt)
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_predictions(r.read(), len(rows), classes)
    from concurrent.futures import ThreadPoolExecutor

    from .image_encode import load, to_pixels, to_png
    enc = load()
    idx = [cols.index(c) for c in enc["columns"]]
    field = os.environ.get("AISTREAM_IMAGE_FIELD", "file")

    def one(row: list) -> dict:
        body, ctype = _multipart(field, "row.png", to_png(to_pixels([row[i] for i in idx], enc)))
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_image_response(r.read(), classes)

    with ThreadPoolExecutor(max_workers=int(os.environ.get("AISTREAM_WORKERS", "4"))) as ex:  # 서빙 대기열(10) 안쪽
        return list(ex.map(one, rows))


def predict(verdicts: list[Verdict], cards_by_id: dict, product: dict, reg: RegIndex) -> dict:
    url = os.environ.get("AISTREAM_URL", "").strip()
    if not url:
        return {"enabled": False, "reason": "AIStream 모델 미연결"}
    try:  # 열 정보 파일·설정 값·모델 장애가 판정 화면을 막지 않게 한다
        cols = columns()
        known = set(cols)
        # 학습 때 없던 인증(새 카드·이름 바뀐 카드)은 원-핫이 전부 0이 되어 엉뚱한 예측이 나오므로 보내지 않는다
        vs = [v for v in verdicts if v.kind != "company_certification" and f"cert_{v.cert_id}" in known]
        skipped = sorted(v.cert_id for v in verdicts if v.kind != "company_certification" and f"cert_{v.cert_id}" not in known)
        rows = feature_rows(vs, cards_by_id, product, reg, cols)
        classes = os.environ.get("AISTREAM_CLASSES", "COND,FAIL,NOT_APPLICABLE,PASS").split(",")
        threshold = float(os.environ.get("AISTREAM_FAIL_THRESHOLD", "0.3"))
        preds = call_model(url, cols, rows, classes, os.environ.get("AISTREAM_FORMAT", "mlflow"),
                           float(os.environ.get("AISTREAM_TIMEOUT", "8")))
    except Exception as e:
        return {"enabled": True, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    results = {}
    for v, pr in zip(vs, preds):
        fail_p = (pr["proba"] or {}).get("FAIL")
        alert = v.status != STATUS_FAIL and (fail_p >= threshold if fail_p is not None else pr["label"] == "FAIL")
        results[v.cert_id] = {**pr, "rule_status": v.status, "agree": pr["status"] == v.status,
                              "fail_proba": fail_p, "hidden_fail_alert": alert}
    return {"enabled": True, "ok": True, "threshold": threshold, "skipped_certs": skipped,
            "n_alerts": sum(r["hidden_fail_alert"] for r in results.values()), "results": results}
