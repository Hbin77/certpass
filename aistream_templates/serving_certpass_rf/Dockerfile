FROM python:3.11

WORKDIR /app

RUN python -m pip install --no-cache-dir uv==0.11.5

COPY pyproject.toml ./

RUN uv sync --no-dev --no-install-project --python "$(command -v python)"

# 빌드 검증은 이미지의 기본 python으로 Click 옵션을 읽으므로 uv 가상환경을 PATH 앞에 둡니다.
ENV PATH="/app/.venv/bin:$PATH"

COPY . ./

ENTRYPOINT ["uv", "run", "--active", "--no-sync", "python", "main.py"]
