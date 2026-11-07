#!/bin/bash
# usage: axput.sh <local file> <remote file> — axgpu 중계가 큰 전송을 끊어 base64 12KB 조각을 명령 인자로 보낸다
set -euo pipefail
f="$1"; r="$2"; T=$(mktemp -d)
base64 < "$f" | tr -d '\n' > $T/b64; split -b 12000 $T/b64 $T/p.
ssh -o BatchMode=yes axgpu "mkdir -p \$(dirname '$r') && rm -f '$r.b64'"
for p in $T/p.*; do c=$(cat $p); for t in 1 2 3; do ssh -o BatchMode=yes axgpu "printf %s '$c' >> '$r.b64'" && break; sleep 2; done; done
ssh -o BatchMode=yes axgpu "base64 -d '$r.b64' > '$r' && rm '$r.b64' && ls -la '$r'"; rm -rf $T
