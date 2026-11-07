#!/bin/bash
# 대회 서버(axgpu)로 프로젝트를 올린다. 중계 서버가 큰 stdin 전송을 끊어서, base64를 잘게 나눠 명령 인자로 보낸다.
# 사용: deploy/push_axgpu.sh [원격폴더=/data/certcheck] [조각크기=12000]  (40KB 인자·20KB stdin은 끊김, 12KB는 통과)
set -euo pipefail
cd "$(dirname "$0")/.."
REMOTE=${1:-/data/certcheck}
CHUNK=${2:-12000}
# 원격 명령 문자열에 들어가므로 경로에 쓰는 글자만 받는다(따옴표·공백·$·; 로 원격 명령이 바뀌지 않게, -로 시작하면 옵션이 됨)
case "$REMOTE" in
  "" | -* | *[!A-Za-z0-9_./-]*) echo "원격 폴더에 쓸 수 없는 글자가 있습니다: $REMOTE" >&2; exit 1 ;;
esac
case "$CHUNK" in  # 산술 확장 $(( ))은 값 속 명령도 실행하므로 숫자만
  "" | 0* | *[!0-9]*) echo "조각 크기는 1 이상의 숫자여야 합니다: $CHUNK" >&2; exit 1 ;;
esac
TMP=$(mktemp -d)
RTMP=""
cleanup() {
  rm -rf "$TMP"
  if [ -n "$RTMP" ]; then ssh -o BatchMode=yes axgpu "rm -f '$RTMP'" || true; fi
}
trap cleanup EXIT
# 성분규제 통합표는 JP 보강본이 있으면 원본을 빼고 보낸다(앱은 보강본을 먼저 읽음)
EXTRA=()
[ -f "data/regs/성분규제_통합표_JP보강.csv" ] && EXTRA+=(--exclude "data/regs/성분규제_통합표.csv")
# 서버 판정에 필요 없는 AI Hub 파생 자료(포장 OCR 글자·변형 표기)는 보내지 않는다. 유해성 표(71916)만 특징 계산에 쓴다
EXTRA+=(--exclude "data/aihub/633_*")
tar --exclude ".venv" --exclude "data/private" --exclude "out" --exclude "__pycache__" --exclude ".git" --exclude ".pytest_cache" --exclude ".env*" "${EXTRA[@]}" -czf "$TMP/p.tgz" .
base64 < "$TMP/p.tgz" | tr -d '\n' > "$TMP/p.b64"
SIZE=$(wc -c < "$TMP/p.b64" | tr -d ' ')
N=$(( (SIZE + CHUNK - 1) / CHUNK ))
echo "압축 $(wc -c < "$TMP/p.tgz" | tr -d ' ')B → base64 ${SIZE}B → ${N}조각"
# 원격 임시 파일은 고정 경로 대신 mktemp(권한 600, 남이 미리 만든 파일·링크에 이어 쓰지 않음). 끝나거나 실패하면 지운다
RTMP=$(ssh -o BatchMode=yes axgpu "mktemp /tmp/certcheck-push.XXXXXXXX")
case "${RTMP#/tmp/certcheck-push.}" in  # 접두사 뒤가 영숫자일 때만 원격 명령에 넣는다
  "$RTMP" | "" | *[!A-Za-z0-9]*) echo "원격 임시 파일을 만들지 못했습니다: $RTMP" >&2; RTMP=""; exit 1 ;;
esac
split -b "$CHUNK" "$TMP/p.b64" "$TMP/part."
i=0
for f in "$TMP"/part.*; do
  PART=$(cat "$f")
  for try in 1 2 3; do
    if ssh -o BatchMode=yes axgpu "printf %s '$PART' >> '$RTMP'"; then break; fi
    echo "조각 $i 재시도 $try"; sleep 2
  done
  i=$((i+1))
done
ssh -o BatchMode=yes axgpu "test \$(wc -c < '$RTMP') -eq $SIZE && mkdir -p '$REMOTE' && base64 -d '$RTMP' | tar xzf - -C '$REMOTE' && echo '원격 풀기 완료'"
