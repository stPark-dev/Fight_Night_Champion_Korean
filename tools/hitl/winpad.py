"""Windows용 RPCS3 런타임 검증 보조: 게임 창에 키 입력(SendInput)을 보내고 창을 캡처한다.

검수 전용 키보드 프로필(fnc_qa)로 실행했을 때의 키: Return=START, x=✕, c=○, z=□, v=△,
방향키=십자키, q/e=L1/R1, t/r=L2/R2, w/a/s/d=왼쪽 스틱, i/j/k/l=오른쪽 스틱, space=SELECT.

사용: python tools/hitl/winpad.py <키>[:대기초][*반복] ... [--shot 파일.png] [--fg]
  예: python tools/hitl/winpad.py Down:0.5 x:3 --shot work/runlogs/menu.png

기본은 백그라운드 방식: 창을 앞으로 가져오지 않고 키 메시지를 창에 직접 보내고(PostMessage),
창 내용만 캡처한다(PrintWindow). 그동안 다른 프로그램을 써도 된다(게임 창 최소화만 피할 것).
--fg 는 창을 앞으로 가져와 SendInput 으로 누르고 화면 영역을 캡처하는 예전 방식.
"""
import argparse
import ctypes
import time
from ctypes import wintypes
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image, ImageGrab

TITLE = "BLJM60267"
VK = {"Return": 0x0D, "Escape": 0x1B, "space": 0x20, "Backspace": 0x08,
      "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28}
EXTENDED = {"Left", "Up", "Right", "Down"}

user32 = ctypes.WinDLL("user32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def find_window():
    found = []

    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if TITLE in t and win32gui.IsWindowVisible(h):
            found.append((h, t))
    win32gui.EnumWindows(cb, None)
    # 게임 창(제목에 FPS 표시)을 우선
    found.sort(key=lambda ht: "FPS" not in ht[1])
    return found[0][0] if found else None


def activate(hwnd):
    if win32gui.IsIconic(hwnd):  # 최소화된 경우만 복원(최대화 창에 SW_RESTORE 를 주면 크기가 줄어든다)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    # 다른 창이 포그라운드일 때 SetForegroundWindow 가 거부되지 않도록 Alt 를 한 번 눌렀다 뗀다
    _send(0x12, False, False)
    _send(0x12, True, False)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except win32gui.error:  # 포커스 전환이 일시적으로 거부되면 한 번 더 시도
        time.sleep(0.5)
        win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def _send(vk, up, ext):
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if up:
        flags |= 0x0002
    if ext:
        flags |= 0x0001
    inp = INPUT(type=1, ki=KEYBDINPUT(0, scan, flags, 0, 0))
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def press(key, hold=0.12):
    vk = VK.get(key) or ord(key.upper())
    ext = key in EXTENDED
    _send(vk, False, ext)
    time.sleep(hold)
    _send(vk, True, ext)


def post(hwnd, key, hold=0.12):
    """포커스 없이 창에 키를 보낸다(lParam 에 스캔코드를 넣어야 Qt 가 키를 구분한다)."""
    vk = VK.get(key) or ord(key.upper())
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = (1 << 24) if key in EXTENDED else 0
    down = 1 | (scan << 16) | ext
    up = down | (1 << 30) | (1 << 31)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, down)
    time.sleep(hold)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, up)


def shot_bg(hwnd, path):
    """가려져 있어도 창 내용을 캡처(PW_CLIENTONLY | PW_RENDERFULLCONTENT)."""
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    dc = win32ui.CreateDCFromHandle(hdc)
    mem = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc, w, h)
    mem.SelectObject(bmp)
    try:
        if not user32.PrintWindow(hwnd, mem.GetSafeHdc(), 3):
            raise OSError("PrintWindow 실패")
        info = bmp.GetInfo()
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                               bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        mem.DeleteDC()
        dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc)
        win32gui.DeleteObject(bmp.GetHandle())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def shot(hwnd, path):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    x, y = win32gui.ClientToScreen(hwnd, (l, t))
    img = ImageGrab.grab(bbox=(x, y, x + r - l, y + b - t), all_screens=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def run(steps, shot_path=None, fg=False):
    hwnd = find_window()
    if not hwnd:
        raise SystemExit(f"'{TITLE}' 창 없음")
    if win32gui.IsIconic(hwnd):
        raise SystemExit("게임 창이 최소화되어 있음(최소화하면 화면이 그려지지 않는다)")
    if fg:
        activate(hwnd)
    for step in steps:
        rep = 1
        if "*" in step:
            step, n = step.rsplit("*", 1)
            rep = int(n)
        key, _, wait = step.partition(":")
        for _ in range(rep):
            press(key) if fg else post(hwnd, key)
            time.sleep(float(wait or 0.4))
    if shot_path:
        print(shot(hwnd, shot_path) if fg else shot_bg(hwnd, shot_path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*")
    ap.add_argument("--shot")
    ap.add_argument("--fg", action="store_true", help="창을 앞으로 가져와 조작(예전 방식)")
    args = ap.parse_args()
    run(args.steps, args.shot, args.fg)


if __name__ == "__main__":
    main()
