"""Workflow가 주입한 단일 모델 입력 계약을 파싱합니다."""

import json
import os

MODEL_INPUTS_ENV = "MODEL_INPUTS_JSON"
_VERSION_FIELDS = (
    "registeredModelVersionId",
    "mlflowRegisteredModelName",
    "mlflowModelVersion",
    "mountPath",
)


def load_model_input(
    port_name: str,
    raw_value: str | None = None,
    *,
    allow_fresh: bool = False,
) -> dict[str, str]:
    """지정한 portName의 모델 입력을 신 계약으로 검증해 반환합니다."""
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
    if not isinstance(spec, dict):
        raise ValueError(f"{port_name} 모델 입력이 필요합니다.")

    mode = spec.get("mode")
    registered_model_id = spec.get("registeredModelId")
    if not isinstance(registered_model_id, str) or not registered_model_id:
        raise ValueError(f"{port_name}.registeredModelId가 필요합니다.")
    if mode == "FRESH":
        if not allow_fresh:
            raise ValueError(f"{port_name} 입력은 FROM_VERSION이어야 합니다.")
        return {
            "mode": mode,
            "registeredModelId": registered_model_id,
        }
    if mode != "FROM_VERSION":
        raise ValueError(f"{port_name}.mode가 올바르지 않습니다: {mode!r}")

    missing = [
        field
        for field in _VERSION_FIELDS
        if not isinstance(spec.get(field), str) or not spec[field]
    ]
    if missing:
        raise ValueError(f"{port_name} 모델 입력 필드가 누락됐습니다: {missing}")
    if not spec["mountPath"].startswith("/"):
        raise ValueError(f"{port_name}.mountPath는 절대 경로여야 합니다.")
    return {
        field: spec[field]
        for field in ("mode", "registeredModelId", *_VERSION_FIELDS)
    }
