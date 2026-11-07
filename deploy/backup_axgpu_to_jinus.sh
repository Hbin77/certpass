#!/bin/bash
# 팀 GPU 서버(axgpu) /data → jinusubuntu(100.106.185.56) /data2/hbin/axgpu_backup/<시각>/ 백업.
# - 맥을 거쳐 tar를 흘려보낸다(axgpu에서 내려받는 방향은 중계가 끊지 않음, jinusubuntu는 tailscale)
# - 가상환경(.venv*)은 용량만 크고 다시 설치할 수 있어 패키지 목록(pip freeze)만 남긴다
# - ocr/crops·ocr/det는 jinusubuntu ai633/crops·det에서 만든 것이므로 체크섬만 대조한다
set -euo pipefail
TS=$(date +%Y%m%d_%H%M)
DEST=/data2/hbin/axgpu_backup/$TS
ssh -o BatchMode=yes jinusubuntu "mkdir -p $DEST"
# 1) 가상환경 패키지 목록
ssh -o BatchMode=yes axgpu 'cd /data && for v in .venv-gpu ocr/.venv ocr/.venv-pkg certcheck/.venv; do [ -x $v/bin/python ] && { echo "## $v"; /data/tools/uv pip freeze --python $v/bin/python 2>/dev/null; }; done' \
  | ssh -o BatchMode=yes jinusubuntu "cat > $DEST/venv_freeze.txt"
# 2) 나머지 전부(가상환경·학습 데이터 제외)
ssh -o BatchMode=yes axgpu 'cd /data && tar czf - --exclude=".venv*" --exclude="ocr/crops" --exclude="ocr/det" --exclude="__pycache__" .' \
  | ssh -o BatchMode=yes jinusubuntu "mkdir -p $DEST/data && tar xzf - -C $DEST/data"
# 3) 대조: 파일 수·크기 합, 학습 데이터 체크섬
ssh -o BatchMode=yes axgpu 'cd /data && find . -path "*/.venv*" -prune -o -path ./ocr/crops -prune -o -path ./ocr/det -prune -o -name __pycache__ -prune -o -type f -printf "%s\n" | awk "{n++; s+=\$1} END {print n, s}"' > /tmp/axgpu_count.txt
ssh -o BatchMode=yes jinusubuntu "cd $DEST/data && find . -type f -printf '%s\n' | awk '{n++; s+=\$1} END {print n, s}'" > /tmp/jinus_count.txt
ssh -o BatchMode=yes axgpu 'cd /data/ocr && md5sum crops/* det/*' | sed 's#^\([0-9a-f]*\)  \(crops\|det\)/#\1  \2/#' > /tmp/axgpu_md5.txt
ssh -o BatchMode=yes jinusubuntu 'cd /data2/hbin/aihub/ai633 && md5sum crops/* det/*' > /tmp/jinus_md5.txt
echo "파일 수·크기 axgpu: $(cat /tmp/axgpu_count.txt) / 백업: $(cat /tmp/jinus_count.txt)"
diff /tmp/axgpu_md5.txt /tmp/jinus_md5.txt && echo "학습 데이터 체크섬 일치(crops·det 10개 파일)" || echo "학습 데이터 체크섬 불일치"
ssh -o BatchMode=yes jinusubuntu "cd /data2/hbin/axgpu_backup && ln -sfn $TS latest && du -sh $DEST && wc -l $DEST/venv_freeze.txt"
echo BACKUP_DONE $DEST
