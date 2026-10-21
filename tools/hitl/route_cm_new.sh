#!/bin/bash
# RPCS3에서 타이틀 → 챔피언 모드 새 게임 → 프롤로그 FMV 시작까지 진행. 사용: route_cm_new.sh <작업디렉터리>
set -u
w=$1; mkdir -p "$w"
here=$(dirname "$0"); py="$here/../../.venv/bin/python"; pad="$py $here/pad.py"; H="$here/press_until_change.sh"
bright() { convert "$1" -crop "$2" -colorspace gray -format "%[fx:mean>$3]" info:; }
is_dialog() { [ "$(bright "$1" 600x60+340+250 0.15)" = 1 ]; }   # 화면 중앙 안내창
bar() { [ "$(bright "$1" 600x10+300+605 0.55)" = 1 ]; }          # 메뉴 화면 하단 흰색 바
is_menu() { bar "$1" && [ "$(bright "$1" 500x80+170+130 0.2)" = 1 ]; }   # 메인 메뉴 첫 항목
$pad --shot "$w/t.png" >/dev/null 2>&1
if ! is_menu "$w/t.png"; then
until $pad --shot "$w/t.png" >/dev/null 2>&1 && [ "$(bright "$w/t.png" 400x80+440+510 0.06)" = 1 ] \
      && [ "$(convert "$w/t.png" -colorspace gray -format '%[fx:mean<0.3]' info:)" = 1 ]; do sleep 3; done
echo "[title]"
for i in $(seq 1 6); do   # 타이틀 문구는 깜빡이므로 화면 변화 대신 안내창/메뉴 출현으로 판정
  $pad Return:5 --shot "$w/1.png" >/dev/null 2>&1
  is_dialog "$w/1.png" || is_menu "$w/1.png" && break
done
ok=0
for i in $(seq 1 30); do   # 자동저장 안내가 있으면 닫고, 메인 메뉴까지 대기
  $pad --shot "$w/m.png" >/dev/null 2>&1 || continue
  is_menu "$w/m.png" && { ok=1; break; }
  is_dialog "$w/m.png" && $pad x:3 >/dev/null
  sleep 3
done
[ $ok = 1 ] || { echo "메인 메뉴 도달 실패"; exit 1; }
fi
echo "[menu]"
champ_selected() { [ "$(convert "$1" -crop 420x50+180+210 -format '%[fx:(mean.r-mean.b)>0.15]' info:)" = 1 ]; }
for i in $(seq 1 8); do   # 메뉴 커서는 마지막 위치를 기억하므로 CHAMPION MODE 줄이 금색이 될 때까지 이동
  $pad --shot "$w/c.png" >/dev/null 2>&1 && champ_selected "$w/c.png" && break
  $pad Down:1.2 >/dev/null
done
champ_selected "$w/c.png" || { echo "CHAMPION MODE 선택 실패"; exit 1; }
$H x "$w/2.png" 3 6   # 챔피언 모드
$H x "$w/3.png" 3 5   # 새 챔피언
$H x "$w/4.png" 3 8   # 난이도
$H x "$w/5.png" 3 4   # 새 저장 슬롯
$H x "$w/6.png" 3 6   # 저장 확인 → 이름 입력
$H Return "$w/7.png" 4 3   # DONE
$H x "$w/8.png" 3 2   # 저장 확인 → 프롤로그
echo "[prologue]"
