"""요청·응답 스키마입니다. CertPass 앱(certcheck/ml_client.py)이 보내는 형식에 맞춥니다."""

from pydantic import BaseModel, Field, model_validator


class DataFrameSplit(BaseModel):
    columns: list[str] = Field(..., min_length=1, description="특징 열 이름")
    data: list[list[float]] = Field(..., description="행마다 columns 순서의 값")


class PredictRequest(BaseModel):
    """dataframe_split(MLflow 방식, 앱 기본값)과 instances(행 객체 목록) 중 하나만 보낸다."""

    dataframe_split: DataFrameSplit | None = None
    instances: list[dict[str, float]] | None = None

    @model_validator(mode="after")
    def _one_of(self):
        if (self.dataframe_split is None) == (self.instances is None):
            raise ValueError("dataframe_split과 instances 중 하나만 보내야 합니다.")
        return self


class PredictResponse(BaseModel):
    predictions: list[dict[str, str | float]] = Field(..., description="행마다 label과 proba_<클래스>")
    classes: list[str]
    model: dict[str, str | int]
    ignored_columns: list[str] = Field(default_factory=list, description="모델이 쓰지 않아 무시한 열")
