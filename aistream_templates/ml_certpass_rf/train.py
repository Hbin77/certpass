"""모델 학습 진입점입니다(7팀 CertPass 인증 판정 랜덤포레스트).

빌드는 click만 설치된 환경에서 이 파일을 실행해 옵션을 읽습니다.
파일 맨 위에는 click만 import하고, 실제 학습 코드는 main() 안에서 import하세요.
"""

import click


@click.command()
@click.option("--n_estimators", type=click.IntRange(10, 2000), default=300, help="랜덤포레스트 트리 수")
@click.option("--min_samples_leaf", type=click.IntRange(1, 100), default=2, help="잎 노드 최소 표본 수")
@click.option("--max_depth", type=click.IntRange(0, 200), default=0, help="트리 최대 깊이(0이면 제한 없음)")
@click.option("--random_state", type=click.INT, default=0, help="난수 시드")
def main(n_estimators, min_samples_leaf, max_depth, random_state):
    """학습용 CSV로 랜덤포레스트를 학습하고 평가용 CSV로 평가해 MLflow에 기록합니다."""

    from src.train_runtime import run_training

    run_training(
        n_estimators=n_estimators,
        min_samples_leaf=min_samples_leaf,
        max_depth=max_depth or None,
        random_state=random_state,
    )


if __name__ == "__main__":
    main()
