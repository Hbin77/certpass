"""서빙 진입점입니다(7팀 CertPass 인증 판정 랜덤포레스트).

Dockerfile·deployment.yaml이 이 파일을 실행합니다.
빌드는 click만 설치된 환경에서 이 파일을 실행해 옵션을 읽습니다.
파일 맨 위에는 click만 import하고, 실제 서빙 코드는 main() 안에서 import하세요.
"""

import click


@click.command()
@click.option("--max_rows", type=click.IntRange(1, 100000), default=5000, help="요청 한 번에 받을 최대 행 수")
@click.option("--n_jobs", type=click.IntRange(1, 64), default=2, help="랜덤포레스트 추론에 쓸 스레드 수(결과는 같고 속도만 다름)")
@click.option("--max_concurrency", type=click.IntRange(1, 32), default=2, help="replica 하나에서 동시에 계산할 요청 수(초과 요청은 대기)")
def main(max_rows, n_jobs, max_concurrency):
    """인증 판정 모델 서빙을 시작합니다."""

    from src.serving_runtime import run_serving

    run_serving(max_rows=max_rows, n_jobs=n_jobs, max_concurrency=max_concurrency)


if __name__ == "__main__":
    main()
