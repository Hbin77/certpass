#!/bin/bash
# 데모 제품 AI 판정 설명을 미리 만들어 out/explain_cache.json에 남긴다(웹을 다시 켜도 바로 뜸). axgpu에서 실행:
#   cd /data/certcheck && setsid nohup bash deploy/warm_explain.sh D3 D5 D1 D2 D4 > out/warm_explain.log 2>&1 &
# 방문자별 분당 6건 상한(AGENTSTREAM_RATE_PER_CLIENT_MIN) 안쪽으로 11초 간격. 이미 캐시에 있으면 바로 넘어간다.
cd "$(dirname "$0")/.." || exit 1
PORT=${PORT:-8501}
BASE="http://127.0.0.1:$PORT${CERTCHECK_BASE:-/i/FBi4CwFvT4Pe38Xd}"
IDS=$(curl -s "$BASE/api/certs" | .venv/bin/python -c "import json,sys; print(' '.join(c['id'] for c in json.load(sys.stdin) if c.get('kind') != 'company_certification'))")
for pid in "${@:-D3}"; do
  case "$pid" in *[!A-Za-z0-9_-]*) echo "제품 id 형식 오류: $pid"; continue ;; esac
  for cid in $IDS; do
    r=$(curl -s -m 150 "$BASE/api/explain-demo/$pid/$cid" | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('cached' if d.get('cached') else ('ok' if d.get('ok') else 'fail ' + str(d.get('error'))[:60]))")
    echo "$(date +%H:%M:%S) $pid $cid $r"
    [ "$r" = "cached" ] || sleep 11
  done
done
echo "끝 $(date +%H:%M:%S)"
