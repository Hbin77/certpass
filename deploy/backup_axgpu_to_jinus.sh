#!/bin/bash
# 팀 GPU 서버(axgpu) /data → jinusubuntu(팀 백업 서버, ssh 설정의 호스트 이름) /data2/hbin/axgpu_backup/<시각>/ 백업.
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
# 2) 나머지 전부(가상환경·학습 데이터·내려받기 캐시 제외. /data/.cache는 운영진 안내 cp -a 뒤 8GB가 넘고 다시 받을 수 있다)
#    중계가 수백 MB 연속 전송을 중간에 끊으므로(2026-11-07 두 번 실패) axgpu에서 묶어 40MB 조각으로 나눈 뒤
#    조각마다 체크섬을 맞춰 받고(최대 5번), 맥에서 합쳐 jinusubuntu로 보낸다
ssh -o BatchMode=yes axgpu 'rm -rf /data/tmp/bk && mkdir -p /data/tmp/bk && cd /data && tar czf /data/tmp/bk/data.tgz --exclude=".venv*" --exclude="./.cache" --exclude="./tmp" --exclude="ocr/crops" --exclude="ocr/det" --exclude="__pycache__" . && cd /data/tmp/bk && split -b 40M data.tgz part. && md5sum data.tgz part.* > md5.txt'
L=$(mktemp -d)
ssh -o BatchMode=yes axgpu 'cat /data/tmp/bk/md5.txt' > "$L/md5.txt"
for p in $(awk '{print $2}' "$L/md5.txt" | grep '^part\.'); do
  want=$(awk -v f="$p" '$2 == f {print $1}' "$L/md5.txt")
  for t in 1 2 3 4 5; do
    ssh -o BatchMode=yes -o ServerAliveInterval=30 axgpu "cat /data/tmp/bk/$p" > "$L/$p" 2>/dev/null || true
    [ "$(md5 -q "$L/$p")" = "$want" ] && break
    echo "$p 재시도 $t"
  done
  [ "$(md5 -q "$L/$p")" = "$want" ] || { echo "$p 받기 실패"; exit 1; }
done
cat "$L"/part.* > "$L/data.tgz"
[ "$(md5 -q "$L/data.tgz")" = "$(awk '$2 == "data.tgz" {print $1}' "$L/md5.txt")" ] || { echo "합친 묶음 체크섬 불일치"; exit 1; }
scp -q "$L/data.tgz" jinusubuntu:$DEST/data.tgz
ssh -o BatchMode=yes jinusubuntu "mkdir -p $DEST/data && tar xzf $DEST/data.tgz -C $DEST/data && rm $DEST/data.tgz"
ssh -o BatchMode=yes axgpu 'rm -rf /data/tmp/bk'; rm -rf "$L"
# 3) 대조: 파일 수·크기 합, 학습 데이터 체크섬
ssh -o BatchMode=yes axgpu 'cd /data && find . -path "*/.venv*" -prune -o -path ./.cache -prune -o -path ./tmp -prune -o -path ./ocr/crops -prune -o -path ./ocr/det -prune -o -name __pycache__ -prune -o -type f -printf "%s\n" | awk "{n++; s+=\$1} END {print n, s}"' > /tmp/axgpu_count.txt
ssh -o BatchMode=yes jinusubuntu "cd $DEST/data && find . -type f -printf '%s\n' | awk '{n++; s+=\$1} END {print n, s}'" > /tmp/jinus_count.txt
ssh -o BatchMode=yes axgpu 'cd /data/ocr && md5sum crops/* det/*' | sed 's#^\([0-9a-f]*\)  \(crops\|det\)/#\1  \2/#' > /tmp/axgpu_md5.txt
ssh -o BatchMode=yes jinusubuntu 'cd /data2/hbin/aihub/ai633 && md5sum crops/* det/*' > /tmp/jinus_md5.txt
echo "파일 수·크기 axgpu: $(cat /tmp/axgpu_count.txt) / 백업: $(cat /tmp/jinus_count.txt)"
diff /tmp/axgpu_md5.txt /tmp/jinus_md5.txt && echo "학습 데이터 체크섬 일치(crops·det 10개 파일)" || echo "학습 데이터 체크섬 불일치"
ssh -o BatchMode=yes jinusubuntu "cd /data2/hbin/axgpu_backup && ln -sfn $TS latest && du -sh $DEST && wc -l $DEST/venv_freeze.txt"
echo BACKUP_DONE $DEST
