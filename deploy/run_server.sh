#!/bin/bash
# 대회 서버에서 certcheck를 8501 포트(공개 URL)로 띄운다. 기존 프로세스는 내리고 다시 띄운다.
# 공개 URL: https://devopen-gpu.jntp-ax.or.kr/i/FBi4CwFvT4Pe38Xd/  (프록시가 접두사를 그대로 넘김 → 접두사 마운트)
cd "$(dirname "$0")/.." || exit 1
PORT=${PORT:-8501}
export CERTCHECK_BASE=${CERTCHECK_BASE:-/i/FBi4CwFvT4Pe38Xd}
# 서빙 주소·기준값은 저장소에 올리지 않는 deploy/server.env에서 읽는다(인증 없는 서빙 주소라 공개 저장소에 두지 않음).
# 형식은 deploy/server.env.example 참고. 파일이 없으면 AIStream 모델 없이 규칙 판정만 한다.
[ -f deploy/server.env ] && . deploy/server.env
# AgentStream(LLM 판정 설명) Key·챗봇 ID는 .env.agentstream(권한 600, push_axgpu.sh가 .env*는 보내지 않아 덮어쓰지 않음)에서 읽는다.
# 형식은 deploy/agentstream.env.example 참고. 파일이 없으면 설명 칸만 숨겨지고 판정은 그대로 된다.
[ -f .env.agentstream ] && set -a && . ./.env.agentstream && set +a
pkill -f "uvicorn certcheck.app:" 2>/dev/null
sleep 1
mkdir -p out
setsid nohup .venv/bin/uvicorn certcheck.app:asgi --host 0.0.0.0 --port "$PORT" \
  --proxy-headers --forwarded-allow-ips="*" > out/server.log 2>&1 < /dev/null &
echo $! > out/server.pid
sleep 3
curl -s "http://127.0.0.1:$PORT$CERTCHECK_BASE/api/health" && echo
