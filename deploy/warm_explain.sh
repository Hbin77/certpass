#!/bin/bash
# 데모 제품 AI 판정 설명을 미리 만들어 out/explain_cache.json에 남긴다(웹을 다시 켜도 바로 뜸). axgpu에서 실행:
#   cd /data/certcheck && setsid nohup bash deploy/warm_explain.sh D3 D5 D1 D2 D4 > out/warm_explain.log 2>&1 &
# 방문자별 분당 6건 상한(AGENTSTREAM_RATE_PER_CLIENT_MIN) 안쪽으로 11초 간격. 이미 캐시에 있으면 바로 넘어간다.
# LLM_RATE_LIMITED('순간 요청 한도'라고 나오지만 7팀 일간 토큰 한도 12M 소진일 때도 같은 오류, 2026-11-07 확인)에 걸리면
# 같은 건을 60·120·240초 쉬었다가 다시 시도하고, 그래도 안 되면 멈춘다(KST 자정에 초기화). 해당 없음 판정은 서버가 설명을 생략(skip).
cd "$(dirname "$0")/.." || exit 1
echo $$ > out/warm_explain.pid
PORT=${PORT:-8501}
BASE="http://127.0.0.1:$PORT${CERTCHECK_BASE:-/i/FBi4CwFvT4Pe38Xd}"
IDS=$(curl -s "$BASE/api/certs" | .venv/bin/python -c "import json,sys; print(' '.join(c['id'] for c in json.load(sys.stdin) if c.get('kind') != 'company_certification'))")
one() {
  curl -s -m 150 "$BASE/api/explain-demo/$1/$2" | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('skip' if d.get('enabled') is False else 'cached' if d.get('cached') else ('ok' if d.get('ok') else 'fail ' + str(d.get('error'))[:60]))"
}
for pid in "${@:-D3}"; do
  case "$pid" in *[!A-Za-z0-9_-]*) echo "제품 id 형식 오류: $pid"; continue ;; esac
  for cid in $IDS; do
    r=$(one "$pid" "$cid")
    for wait in 60 120 240; do  # 한도·밀림일 때만 쉬었다가 같은 건을 다시(서버 하루 상한은 기다려도 안 풀려 바로 멈춤)
      case "$r" in *"오늘 새로"*) break ;; "fail RateLimit"*) echo "$(date +%H:%M:%S) $pid $cid 한도 — ${wait}초 쉼"; sleep "$wait"; r=$(one "$pid" "$cid") ;; *) break ;; esac
    done
    echo "$(date +%H:%M:%S) $pid $cid $r"
    case "$r" in *"오늘 새로"*) echo "서버 하루 상한 — 멈춤"; exit 0 ;; "fail RateLimit"*) echo "7분 기다려도 한도가 안 풀림(일간 토큰 한도 소진으로 봄) — 멈춤"; exit 0 ;; esac
    case "$r" in cached|skip) ;; *) sleep 11 ;; esac
  done
done
echo "끝 $(date +%H:%M:%S)"
