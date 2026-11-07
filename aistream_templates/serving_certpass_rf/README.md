# AIStream 서빙 하네스 적용 안내

등록 이름은 `aistream-serving`이며 현재 하네스 버전은 `v0.0.1`입니다. 이 묶음은 AIStream 모델 서빙의 구현·검토·검증·명세 작성을 돕는 지침과 전문 스킬입니다.

## 등록된 스킬 사용

대상 서빙 프로젝트를 열고 다음처럼 요청합니다.

> $aistream-serving 현재 서빙 템플릿의 모델 입력 및 빌드 연결을 검토해줘. 코드는 아직 수정하지 마.

> $aistream-serving이 모델을 배포해줘.

이 폴더의 [AGENTS.md](AGENTS.md)에서 작업 흐름을 확인하고, 요청에 맞는 전문 스킬을 선택해 읽습니다. 하네스 자료 위치와 실제 작업 대상 프로젝트 root를 구별합니다. 같은 이름의 전역 전문 스킬이 있더라도 이 묶음의 `.agents/skills/`를 사용합니다. 호출만으로 대상 프로젝트에 지침을 복사하거나 기존 파일을 덮어쓰지 않습니다.

## 주요 작업 규칙

- **작업 환경**: 이미 SSH로 접속된 서버의 현재 작업 경로에서 기존 코드와 지침을 확인하고 템플릿을 직접 작성·수정합니다. 별도 연결·재접속이 필요한 경우에만 [SSH 접속·재시도 규칙](.agents/references/ssh-connection.md)을 따릅니다.
- **template-inout 예외**: `template-inout.yaml`, `template-inout.yml`, `template-inout.yaml.j2`, `template-inout.yml.j2`는 YAML 파일 종류에 따른 별도 승인 제약에서 제외합니다. 사용자가 요청한 수정 범위에서 변경하며, 포트·모델 입력·입출력 소비 계약과 명세 일치는 계속 검증합니다. 다른 Docker/YAML 보호 파일에는 기존 승인 절차를 적용합니다.
- **배포 요청 해석**: “배포”, “배포해줘”, “모델 배포”는 모델 서빙 구현·실행·검증을 의미합니다. 필요한 서빙 작업을 진행하고 실제 AIStream 플랫폼의 서비스 생성·등록·관리 API 호출로 확대하지 않습니다. 실제 플랫폼 배포를 명시하면 사람이 진행할 절차와 확인 사항을 인계합니다.

세부 작업 경계와 완료 기준은 [AGENTS.md](AGENTS.md) 및 [공통 작업 계약](.agents/references/common-contract.md)을 따릅니다. 검토 요청을 코드 수정 승인으로 해석하지 않습니다.

## 서빙 코드 변경 이력 자동 기록

`modified_version.md`는 이 스킬로 작업하는 **실제 서빙 템플릿 코드의 변경 이력**입니다. 서빙 코드·설정을 최초 생성하거나 수정할 때 에이전트가 대상 프로젝트 root에 자동 생성·갱신하며, 별도 기록 요청을 기다리지 않습니다.

버전·변경 시각(KST)·작업 사용자·기록 작성자·변경 파일과 함수·수정 방식과 이유·기존 동작 영향·검증 결과를 남깁니다. 기존 기록은 보존하고 새 작업을 추가합니다. 사용자명이 확인되지 않으면 추정하지 않고 `미확인`으로 표시하며 Codex 수행·작성 사실을 함께 남깁니다.

검토만 하거나 코드 변경이 없는 작업에는 서버 코드 이력을 새로 만들지 않습니다. 프로젝트가 기존 `CHANGELOG.md` 등을 이력 원본으로 지정했다면 그 문서에 기록합니다. 하네스 자체 버전이나 릴리스 이력은 이 파일에 넣지 않습니다. 상세 절차와 최초 생성 표는 [서빙 코드 변경 이력](.agents/references/serving-change-history.md)에 있습니다.

## 다른 프로젝트에 파일로 적용

1. 이 하네스 폴더의 `AGENTS.md`와 숨김 폴더 `.agents/`를 대상 프로젝트 root에 배치합니다. 하네스 상위 폴더째 하위에 넣지 않습니다. `modified_version.md`는 실제 코드 생성·수정 시 대상 프로젝트에 자동 생성되므로 하네스에서 복사하지 않습니다.
2. 기존 지침·동명 스킬이 있으면 내용을 비교·병합하고 대상 프로젝트의 기존 변경 이력은 보존합니다. 하네스 설치만으로 서버 코드 변경 이력을 생성하거나 기존 이력을 덮어쓰지 않습니다.
3. 대상 프로젝트에서 다음처럼 요청합니다.

> AGENTS.md와 프로젝트의 .agents/skills를 읽고, 현재 서빙 템플릿의 모델 입력 및 빌드 연결을 검토해줘. 코드는 아직 수정하지 마.

이 파일 배치 방식에는 전역 스킬 설치가 필수가 아닙니다. 등록된 `$aistream-serving` 방식과 프로젝트 파일 배치 방식 중 실제 사용 방식에 맞게 지침 경로를 선택합니다.

## 포함 구성

- [AGENTS.md](AGENTS.md): 메인 작업 지침, 배포 요청 해석, SSH 규칙 연결, 파일 변경 경계와 검증 기준.
- `.agents/skills/`: 전문 스킬 8개 및 개별 참조 파일.
- `.agents/references/`: 공통 작업 계약·변경 이력·SSH 접속 규칙.

| 전문 스킬 | 역할 |
| --- | --- |
| [aistream-mlflow](.agents/skills/aistream-mlflow/SKILL.md) | 모델 전달 정보·MLflow 로딩 연결 |
| [aistream-volume](.agents/skills/aistream-volume/SKILL.md) | 포트·마운트·파일 입출력 연결 |
| [aistream-serving](.agents/skills/aistream-serving/SKILL.md) | 모델 서빙·API·초기화·동시성 |
| [aistream-parameters](.agents/skills/aistream-parameters/SKILL.md) | Click 옵션부터 최종 사용 함수까지 전달 |
| [aistream-resources](.agents/skills/aistream-resources/SKILL.md) | CPU·RAM·GPU·배치·동시성 비용 검토 |
| [aistream-logic-review](.agents/skills/aistream-logic-review/SKILL.md) | 현재 코드의 처리 흐름·입출력 검토 |
| [aistream-integration-check](.agents/skills/aistream-integration-check/SKILL.md) | 진입점·import·이미지·빌드 연결 검증 |
| [aistream-serving-spec](.agents/skills/aistream-serving-spec/SKILL.md) | 실제 API·모델 생명주기 명세 작성 |

## 포함하지 않는 항목과 검증 범위

템플릿 작성은 현재 작업 경로에서 진행하며 별도의 템플릿 준비 CLI를 요구하지 않습니다. 대상 프로젝트의 Variant와 실행 계약을 확인하고, OpenPlatform에 RAMP 규칙을 임의 적용하지 않습니다.

실제 서빙 코드·모델·데이터·운영 자격증명·Python 의존성은 포함하지 않습니다. 실행 검증에는 대상 프로젝트 환경이 필요합니다. 문서·스킬 형식·참조 링크 검증과 실제 SSH 접속·서버 실행·모델 추론·AIStream 플랫폼 검증 결과는 구별해 보고합니다.

이 폴더의 지침 변경은 다른 프로젝트에 복사된 사본에 자동으로 동기화되지 않습니다.
