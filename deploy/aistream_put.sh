#!/bin/bash
# usage: aput.sh <local file> <remote path>  — 중계가 큰 전송을 끊어 12KB씩 나눠 보낸다
S=$(cd "$(dirname "$0")" && pwd)
H=${AISTREAM_HOST:?td-세션호스트 지정}
f="$1"; r="$2"
ssh -F "$S/aistream_ssh.conf" $H "rm -f '$r.b64'; mkdir -p \$(dirname '$r')" 2>/dev/null
base64 -i "$f" | fold -w 12000 | while read -r line; do
  echo "$line" | ssh -F "$S/aistream_ssh.conf" $H "cat >> '$r.b64'" 2>/dev/null </dev/stdin || { echo FAIL; exit 1; }
done
ssh -F "$S/aistream_ssh.conf" $H "base64 -d '$r.b64' > '$r' && rm '$r.b64' && wc -c '$r'" 2>/dev/null
