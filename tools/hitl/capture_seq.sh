#!/bin/bash
# 사용: capture_seq.sh <출력디렉터리> <횟수> <간격초>  — RPCS3 게임 창을 주기적으로 캡처
out=$1; n=$2; gap=$3; mkdir -p "$out"
here=$(dirname "$0"); py="$here/../../.venv/bin/python"
for i in $(seq -w 1 "$n"); do "$py" "$here/pad.py" --shot "$out/$i.png" >/dev/null 2>&1 || echo "fail $i"; sleep "$gap"; done
