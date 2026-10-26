#!/bin/bash
# 깨끗한 스크린샷: RPCS3 "Screenshot saved" 알림이 사라지도록 간격을 두고, 조건(밝기 영역)이 맞을 때까지 다시 찍는다.
# 사용: clean_shot.sh <출력.png> [영역 WxH+X+Y] [최소밝기] [최대시도=8]
out=$1; crop=${2:-}; min=${3:-0}; tries=${4:-8}
here=$(dirname "$0"); py="$here/../../.venv/bin/python"
for i in $(seq 1 "$tries"); do
  sleep 9
  "$py" "$here/pad.py" --shot "$out" >/dev/null 2>&1 || continue
  [ -z "$crop" ] && exit 0
  [ "$(convert "$out" -crop "$crop" -colorspace gray -format "%[fx:mean>$min]" info:)" = 1 ] && exit 0
done
echo "조건 맞는 화면을 못 찍음: $out"; exit 1
