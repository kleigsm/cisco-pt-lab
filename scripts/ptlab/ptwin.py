#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Low-level Windows input for driving Packet Tracer with ctypes only.

Why this exists: the Windows MCP desktop tools are not always available
(``computer use`` can be off), so the skill needs a fallback that can click,
type, read the clipboard and capture the screen without pywin32.

All coordinates are PHYSICAL screen pixels: the process opts into DPI
awareness at import time, so a screenshot pixel and a click pixel match even
at 125% scaling.
"""
import ctypes
import os
import time
from ctypes import wintypes

from PIL import ImageGrab

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # pragma: no cover - older Windows
    try:
        u32.SetProcessDPIAware()
    except Exception:
        pass

SW_RESTORE = 9
SW_MAXIMIZE = 3
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_TAB = 0x09
VK_SPACE = 0x20
VK_DELETE = 0x2E
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# explicit prototypes: on 64-bit a default c_int return truncates the handle
u32.OpenClipboard.argtypes = [wintypes.HWND]
u32.OpenClipboard.restype = wintypes.BOOL
u32.GetClipboardData.restype = wintypes.HANDLE
u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
u32.SetClipboardData.restype = wintypes.HANDLE
k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wintypes.HGLOBAL
k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
k32.GlobalLock.restype = wintypes.LPVOID
k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


# --------------------------------------------------------------------------- windows
def windows():
    """Visible top-level windows as [(hwnd, title, rect), ...]."""
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                out.append((hwnd, buf.value, rect(hwnd)))
        return True

    u32.EnumWindows(_cb, 0)
    return out


def find(substr, exact=False, include_minimized=False):
    """First visible window whose title matches, or None.

    Minimised windows are skipped by default: Windows parks them at -32000 and
    every click on that rect lands in the void.
    """
    for hwnd, title, r in windows():
        if r[0] <= -30000 and not include_minimized:
            continue
        if (title == substr) if exact else (substr.lower() in title.lower()):
            return hwnd, title, r
    return None


def rect(hwnd):
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def raise_window(hwnd, timeout=1.2):
    """Bring a window to the front and confirm it actually got there.

    SetForegroundWindow is refused for processes that do not own the current
    foreground (our case: a background python driving PT).  The ALT tap lifts
    that restriction; without this, clicks silently land on whatever window is
    in front while the script thinks it drove PT.
    """
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
    if foreground() == hwnd:
        return True
    u32.keybd_event(VK_MENU, 0, 0, 0)
    u32.SetForegroundWindow(hwnd)
    u32.keybd_event(VK_MENU, 0, 2, 0)
    time.sleep(0.1)
    key(VK_ESCAPE, 0.12)      # the ALT tap can open the menu bar; close it
    deadline = time.time() + timeout
    while time.time() < deadline:
        if foreground() == hwnd:
            time.sleep(0.1)
            return True
        time.sleep(0.1)
    # last resort: attach our input queue to the foreground thread
    try:
        fg = foreground()
        tid_fg = u32.GetWindowThreadProcessId(fg, None)
        tid_me = k32.GetCurrentThreadId()
        u32.AttachThreadInput(tid_me, tid_fg, True)
        u32.SetForegroundWindow(hwnd)
        u32.SetFocus(hwnd)
        u32.AttachThreadInput(tid_me, tid_fg, False)
    except Exception:
        pass
    time.sleep(0.2)
    return foreground() == hwnd


def maximize(hwnd):
    u32.ShowWindow(hwnd, SW_MAXIMIZE)
    time.sleep(0.6)


def screen_size():
    return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)


def foreground():
    """HWND of the window that currently owns the foreground."""
    return u32.GetForegroundWindow()


# --------------------------------------------------------------------------- input
def move(x, y):
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.04)


def click(x, y, delay=0.30):
    move(x, y)
    u32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.04)
    u32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(delay)


def dclick(x, y, delay=0.7):
    click(x, y, 0.03)
    click(x, y, delay)


def rclick(x, y, delay=0.4):
    move(x, y)
    u32.mouse_event(8, 0, 0, 0, 0)
    time.sleep(0.04)
    u32.mouse_event(16, 0, 0, 0, 0)
    time.sleep(delay)


def drag(x1, y1, x2, y2, steps=28, delay=0.6):
    move(x1, y1)
    time.sleep(0.15)
    u32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.22)
    for i in range(1, steps + 1):
        u32.SetCursorPos(int(x1 + (x2 - x1) * i / steps),
                         int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.014)
    time.sleep(0.22)
    u32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(delay)


def key(vk, delay=0.05):
    u32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    u32.keybd_event(vk, 0, 2, 0)
    time.sleep(delay)


def combo(*vks):
    for v in vks:
        u32.keybd_event(v, 0, 0, 0)
        time.sleep(0.02)
    for v in reversed(vks):
        u32.keybd_event(v, 0, 2, 0)
        time.sleep(0.02)
    time.sleep(0.15)


def wheel(notches, x=None, y=None):
    if x is not None:
        move(x, y)
    for _ in range(abs(notches)):
        u32.mouse_event(0x0800, 0, 0, 120 if notches > 0 else -120, 0)
        time.sleep(0.08)


def _type_ascii(text, per_char=0.02):
    """Layout-aware typing for widgets that ignore a clipboard paste."""
    for ch in text:
        vk = u32.VkKeyScanW(ord(ch)) & 0xFFFF
        if vk == 0xFFFF:
            continue
        base, shift = vk & 0xFF, (vk >> 8) & 1
        if shift:
            u32.keybd_event(VK_SHIFT, 0, 0, 0)
        u32.keybd_event(base, 0, 0, 0)
        u32.keybd_event(base, 0, 2, 0)
        if shift:
            u32.keybd_event(VK_SHIFT, 0, 2, 0)
        time.sleep(per_char)


# --------------------------------------------------------------------------- clipboard
def clip_get():
    for _ in range(6):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.08)
    else:
        return ''
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ''
        p = k32.GlobalLock(h)
        if not p:
            return ''
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def clip_set(text):
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    for _ in range(6):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.08)
    else:
        raise RuntimeError('cannot open clipboard')
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, size)
        k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        u32.CloseClipboard()


# --------------------------------------------------------------------------- screenshot
def shot(path, box=None):
    """Grab (optionally cropped) screen and save it; returns the PIL image."""
    img = ImageGrab.grab(all_screens=True)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if box:
        img = img.crop(box)
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    img.save(path)
    return img
