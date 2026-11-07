"""Workflow가 주입한 버전 모델 입력 계약을 파싱합니다."""

import json
import os

MODEL_INPUTS_ENV = "MODEL_INPUTS_JSON"
_REQUIRED_FIELDS = (
    "registeredModelId",
    "registeredModelVersionId",
    "mlflowRegisteredModelName",
    "mlflowModelVersion",
    "mountPath",
)


def load_model_input(
    port_name: str = "base_model", raw_value: str | None = None
) -> dict[str, str]:
    """지정한 portName의 FROM_VERSION 모델 입력을 검증해 반환합니다."""
    raw_value = raw_value if raw_value is not None else os.getenv(MODEL_INPUTS_ENV)
    if not raw_value:
        raise ValueError(f"{MODEL_INPUTS_ENV} 환경변수가 필요합니다.")
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{MODEL_INPUTS_ENV}이 올바른 JSON이 아닙니다.") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ValueError(f"{MODEL_INPUTS_ENV}.schemaVersion은 1이어야 합니다.")
    inputs = payload.get("inputs")
    spec = inputs.get(port_name) if isinstance(inputs, dict) else None
    if not isinstance(spec, dict) or spec.get("mode") != "FROM_VERSION":
        raise ValueError(f"{port_name} 입력은 FROM_VERSION이어야 합니다.")
    missing = [
        field
        for field in _REQUIRED_FIELDS
        if not isinstance(spec.get(field), str) or not spec[field]
    ]
    if missing:
        raise ValueError(f"{port_name} 모델 입력 필드가 누락됐습니다: {missing}")
    if not spec["mountPath"].startswith("/"):
        raise ValueError(f"{port_name}.mountPath는 절대 경로여야 합니다.")
    return {field: spec[field] for field in ("mode", *_REQUIRED_FIELDS)}
