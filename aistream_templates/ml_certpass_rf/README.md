# ML 템플릿 시작하기

## 파일 구성

* `train.py`, `evaluate.py` : 학습·평가 Step의 진입점입니다. 맨 위에는 `click`만 import합니다.
* `src/train_runtime.py`, `src/evaluate_runtime.py` : 실제 학습·평가 코드입니다. 각 `main()` 안에서 import합니다.
* `Dockerfile`, `job.yaml`, `pyproject.toml`, `template-inout.yaml` : 빌드와 실행 설정입니다.

루트의 `.py` 파일 하나가 Step 하나입니다. `main.py`와 함께 둘 수 없습니다.

## 진입점 작성 규칙

빌드는 `click`만 설치된 환경에서 진입점 파일을 실행해 옵션을 읽습니다.
`torch` 같은 라이브러리나 `src` 모듈을 파일 맨 위에서 import하면 빌드가 실패합니다.
옵션은 `@click.option`으로 선언하고, 실제 코드는 `main()` 안에서 import하세요.

## 입출력 설정

데이터셋·모델 입출력은 `template-inout.yaml`의 `train`, `evaluate` 아래에 작성합니다.
파일 안의 주석 예시와 `template-inout.md`의 작성 규칙을 참고하세요.

## 의존성 설치하기

```shell
uv sync
```

## 작업 지침과 스킬

이미 SSH로 접속된 서버의 현재 작업 경로에서 [AGENTS.md](AGENTS.md)를 읽고 필요한 `.agents/skills/` 스킬을 선택합니다. 공통 코드 작성 규칙은 [.agents/references/common-contract.md](.agents/references/common-contract.md)에 있습니다.

이 폴더의 `AGENTS.md`와 `.agents/`를 함께 배치하면 형제 템플릿 폴더 없이 사용할 수 있습니다. 공통 스킬은 serving 묶음에서 재사용했으며 사본 간 변경은 자동 동기화되지 않습니다. 실제 실행 코드·환경의 검증은 지침·스킬 검증과 구분합니다.
