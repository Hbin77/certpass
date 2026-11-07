"""서빙 진입점입니다(7팀 화장품 포장 사진 OCR: 글자 위치 찾기 + 글자 읽기 + 전성분 추출).

Dockerfile·deployment.yaml이 이 파일을 실행합니다.
빌드는 click만 설치된 환경에서 이 파일을 실행해 옵션을 읽습니다.
파일 맨 위에는 click만 import하고, 실제 서빙 코드는 main() 안에서 import하세요.
"""

import click


@click.command()
@click.option("--max_mb", type=click.IntRange(1, 32), default=8, help="사진 한 장 최대 크기(MB)")
@click.option("--threads", type=click.IntRange(1, 64), default=4, help="CPU 추론 스레드 수")
@click.option("--max_concurrency", type=click.IntRange(1, 8), default=1, help="replica 하나에서 동시에 읽을 사진 수(초과 요청은 대기)")
def main(max_mb, threads, max_concurrency):
    """포장 사진 OCR 서빙을 시작합니다."""

    from src.serving_runtime import run_serving

    run_serving(max_mb=max_mb, threads=threads, max_concurrency=max_concurrency)


if __name__ == "__main__":
    main()
