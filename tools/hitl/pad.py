"""RPCS3 창에 XTest 키 입력을 보내고 창을 캡처하는 런타임 검증 보조 도구.

사용: .venv/bin/python tools/hitl/pad.py <키>[:대기초] ... [--shot 파일.png]
키 예: Return Up Down Left Right x c z s Escape
"""
import os
import shutil
import sys
import time
from pathlib import Path

from Xlib import X, XK, display, protocol
from Xlib.ext import xtest

TITLE = os.environ.get("FNC_TITLE", "BLJM60267")  # 미국판은 FNC_TITLE=BLUS30608
SHOT_DIR = Path.home() / ".config/rpcs3/screenshots" / TITLE


def find_window(d):
    def walk(w):
        name = w.get_wm_name()
        if isinstance(name, str) and TITLE in name and name.startswith("FPS"):
            return w
        for c in w.query_tree().children:
            r = walk(c)
            if r:
                return r
    return walk(d.screen().root)


def activate(d, win):
    """창 관리자에 정식 활성화 요청. Qt는 X 포커스만으로는 키 입력을 받지 않는다."""
    root = d.screen().root
    atom = d.intern_atom("_NET_ACTIVE_WINDOW")
    ev = protocol.event.ClientMessage(window=win, client_type=atom,
                                      data=(32, [2, X.CurrentTime, 0, 0, 0]))
    root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    d.sync()
    time.sleep(0.3)
    # 활성화 직후 첫 키가 버려지는 경우가 있어, 게임이 쓰지 않는 키로 한 번 흡수한다
    press(d, win, "Scroll_Lock")
    time.sleep(0.2)


def press(d, win, key, hold=0.25):
    code = d.keysym_to_keycode(XK.string_to_keysym(key))
    if not code:
        raise SystemExit(f"알 수 없는 키: {key}")
    xtest.fake_input(d, X.KeyPress, code)
    d.sync()
    time.sleep(hold)
    xtest.fake_input(d, X.KeyRelease, code)
    d.sync()


def main(argv):
    d = display.Display()
    win = find_window(d)
    if win is None:
        raise SystemExit("RPCS3 게임 창 없음")
    shot = None
    if "--shot" in argv:
        i = argv.index("--shot")
        if i + 1 >= len(argv):
            raise SystemExit("--shot 뒤에 파일 경로가 필요함")
        shot = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if argv:
        activate(d, win)
    for item in argv:
        key, _, wait = item.partition(":")
        press(d, win, key)
        time.sleep(float(wait or 0.6))
    if shot:
        take_screenshot(d, win, shot)
        print(shot)


def take_screenshot(d, win, out):
    """RPCS3 내장 스크린샷(F12) 결과를 복사하고 RPCS3 쪽 원본은 지운다. 창이 화면 밖에 있어도 동작."""
    before = set(SHOT_DIR.glob("*.png"))
    activate(d, win)
    for _ in range(3):  # 활성화 직후 첫 키가 무시되는 경우가 있어 재시도
        press(d, win, "F12")
        for _ in range(20):
            new = set(SHOT_DIR.glob("*.png")) - before
            if new:
                src = max(new, key=lambda p: p.stat().st_mtime)
                for _ in range(100):  # PNG 끝(IEND)까지 써질 때까지 대기
                    if src.read_bytes()[-8:-4] == b"IEND":
                        break
                    time.sleep(0.1)
                shutil.copyfile(src, out)
                src.unlink()
                return
            time.sleep(0.1)
    raise SystemExit("스크린샷 생성 안 됨")


if __name__ == "__main__":
    main(sys.argv[1:])
