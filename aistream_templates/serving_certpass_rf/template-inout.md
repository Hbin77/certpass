# template-inout.yaml 작성 가이드

Serving의 입출력 포트와 실행 설정을 적는 파일입니다. 빌드가 이 파일을 읽어 Step의 입출력으로 등록하고,
형식이 맞지 않으면 빌드가 실패합니다. 비워 두면 입출력이 없는 Step이 됩니다.

## 구조

진입점이 `main.py` 하나라서 `inouts`는 목록, `runtime`은 객체로 바로 씁니다.

```yaml
inouts:
  - ioType: INPUT
    portName: model
    kind: MLFLOW_MODEL
    path: /app/volume/models/model
    format: mlflow
    portIdx: 0
  - ioType: OUTPUT
    portName: serving
    kind: SERVING
    format: http
    portIdx: 0
runtime: {}
```

모델 입력은 여러 개 둘 수 있습니다. 포트마다 다른 `path`를 쓰고, 서버를 시작할 때 각 경로에서 모델을 읽습니다.
워크플로에서 이 템플릿으로 Serving을 만들려면 `SERVING` 출력 포트를 하나 둡니다.

## 포트 필드

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `ioType` | 예 | `INPUT` 또는 `OUTPUT` |
| `portName` | 예 | 포트 이름. 같은 방향 안에서 겹치면 안 됩니다. 워크플로 화면과 `MODEL_INPUTS_JSON`의 key로 쓰입니다. |
| `kind` | 예 | 아래 kind 표 중 하나 |
| `path` | kind별 | 컨테이너 안의 절대 경로. 포트끼리 겹치면 안 됩니다. |
| `format` | 아니요 | 데이터 형식(예: `npy`, `csv`, `mlflow`, `http`). 워크플로에서 출력과 입력을 연결할 때 형식이 같아야 하며 `"*"`는 모든 형식과 연결됩니다. 기본값 `"*"` |
| `isRequired` | 아니요 | 워크플로에서 반드시 연결해야 하는 포트인지. 기본값 `true` |
| `portIdx` | 아니요 | 화면에 표시하는 순서. 기본값은 목록 순서 |

## kind

| kind | path | 컨테이너가 받는 방식 |
| --- | --- | --- |
| `DATASET` | 필수 | 입력은 선택한 데이터셋 파일이 `path`에 마운트됩니다. 출력은 `path`에 쓴 파일이 새 데이터셋 버전이 됩니다. |
| `MLFLOW_MODEL` | 필수 | 모델 입력. 선택한 모델 버전의 파일이 `path`에 읽기 전용으로 마운트되고, 모델 정보가 `MODEL_INPUTS_JSON` 환경변수로 전달됩니다. |
| `TRAINED_MODEL` | 쓰지 않음 | 모델 출력, Step당 하나. MLflow Run에 `mlflow.<flavor>.log_model`로 저장한 모델이 등록 모델 버전이 됩니다. `runtime.usesMlflowRun`이 `false`이면 쓸 수 없습니다. |
| `SERVING` | 쓰지 않음 | Serving 템플릿의 출력. 워크플로에서 이 포트로 새 Serving을 만듭니다. |

## runtime

| 키 | 설명 |
| --- | --- |
| `usesMlflowRun` | `true`이면 실행할 때 `EXPERIMENT_NAME`, `RUN_NAME` 환경변수를 넣습니다. 코드는 이 이름으로 MLflow Run을 만들어 기록합니다. MLflow에 기록하는 Step은 `true`로 두고, 이미지에 `mlflow` 3.13 이상을 설치해야 빌드가 통과합니다. |

다른 키는 쓸 수 없습니다.

## 예약된 환경변수

`job.yaml`·`deployment.yaml`의 `env`에는 `EXPERIMENT_NAME`, `RUN_NAME`, `MODEL_INPUTS_JSON`과
`AISTREAM_`, `MLFLOW_`로 시작하는 이름을 쓸 수 없습니다. 플랫폼이 실행할 때 넣는 값입니다.
