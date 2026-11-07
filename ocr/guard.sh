#!/bin/bash
# 학습을 메모리 감시와 함께 띄운다. 서버 여유 메모리가 MIN_MB 아래로 내려가면 학습만 끈다(웹 서비스 보호).
# 사용: MIN_MB=3000 ./guard.sh <로그파일> <명령...>
LOG="$1"; shift
MIN_MB=${MIN_MB:-3000}
setsid "$@" > "$LOG" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$LOG.pid"
while kill -0 "$PID" 2>/dev/null; do
  AVAIL=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  if [ "$AVAIL" -lt "$MIN_MB" ]; then
    echo "[guard] 여유 메모리 ${AVAIL}MB < ${MIN_MB}MB → 학습 중지" >> "$LOG"
    kill -- -"$PID" 2>/dev/null; sleep 5; kill -9 -- -"$PID" 2>/dev/null
    break
  fi
  sleep 2
done
echo "[guard] 종료" >> "$LOG"
