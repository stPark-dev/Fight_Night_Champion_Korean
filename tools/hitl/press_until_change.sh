#!/bin/bash
# 사용: press_until_change.sh <키> <출력.png> [최대시도=5] [대기초=4]
# 키를 누른 뒤 화면(축소 해시)이 바뀔 때까지 재시도. 전환 직후 첫 입력이 무시되는 문제 대응.
key=$1; out=$2; tries=${3:-5}; wait=${4:-4}
here=$(dirname "$0"); py="$here/../../.venv/bin/python"
sig() { convert "$1" -crop 1280x640+0+80 +repage -resize 16x9 -colorspace gray -depth 3 txt:- | md5sum; }
"$py" "$here/pad.py" --shot "$out" >/dev/null || exit 1; before=$(sig "$out")
for i in $(seq 1 "$tries"); do
  "$py" "$here/pad.py" "$key:$wait" --shot "$out" >/dev/null || exit 1
  [ "$(sig "$out")" != "$before" ] && { echo "changed after $i"; exit 0; }
done
echo "no change"; exit 2
