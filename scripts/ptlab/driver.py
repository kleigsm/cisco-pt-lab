#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Packet Tracer semantics: read the CLI, paste config, place devices, connect.

Design rule (learned the hard way): never trust coordinates alone and never
``sleep`` and hope.  Every action here ends in a *read-back* - the terminal text
comes out of the CLI's own Copy button, so a paste, a prompt change or a cable
can be verified instead of assumed.

Quick start::

    from ptlab import driver
    pt = driver.Pt()
    pt.new_file()                       # blank canvas (saves nothing)
    sw = pt.place('2950-24', 760, 300)
    pc = pt.place('PC-PT', 380, 300)
    pt.connect(pc, sw)                  # straight-through, Fa0 -> Fa0/1
    pt.open(pc)                         # double-click a device
    print(pt.paste('show interfaces status'))
"""
import re
import time

from . import ptwin

PROBE = 'show clock\n'          # harmless if a Copy attempt lands on Paste
PROMPT_RE = re.compile(r'^([A-Za-z0-9._-]+)(\([^)]*\))?([#>])\s*$')
ERR_MARKERS = ('% Invalid input', '% Incomplete command', '% Ambiguous command',
               '% Unknown command', 'Translating "')

# palette geometry, measured on a maximised PT 8.2.2 window and expressed as
# offsets from the bottom-left of the main window rect
PAL_FILTER_DX, PAL_FILTER_DY = 90, 68
PAL_ROW_DY = 101
PAL_ICON_X0, PAL_ICON_PITCH = 231, 40
CAT_CONNECTIONS = (123, 99)     # dx, dy from bottom-left
CABLES = {'auto': 0, 'console': 1, 'straight': 2, 'cross': 3,
          'serial-dce': 7, 'serial-dte': 8}


class PtError(RuntimeError):
    pass


STATUS_WORDS = ('connected', 'notconnect', 'disabled', 'err-disabled',
                'monitoring', 'suspended', 'initializing')


def parse_ports(text):
    """[(port, status)] from `show interfaces status`, connected ones first.

    Columns are Port|Name|Status|Vlan|Duplex|Speed|Type and Name is often blank,
    so the status is found by keyword rather than by position.
    """
    rows = []
    for line in (text or '').splitlines():
        m = re.match(r'^(Fa\d+/\d+)\s+(.*)$', line.strip())
        if not m:
            continue
        status = next((t for t in m.group(2).split() if t in STATUS_WORDS), None)
        if status:
            rows.append((m.group(1), status))
    rows.sort(key=lambda r: (r[1] != 'connected', r[0]))
    return rows


def parse_prompt(text):
    """(hostname, mode, symbol) of the last prompt line, or None."""
    for line in reversed((text or '').splitlines()):
        line = line.rstrip()
        if not line:
            continue
        m = PROMPT_RE.match(line)
        if not m:
            return None
        return m.group(1), (m.group(2) or ''), m.group(3)
    return None


class Pt(object):
    def __init__(self, title='Cisco Packet Tracer'):
        hit = ptwin.find(title, include_minimized=True)
        if not hit:
            raise PtError('Packet Tracer window not found - start it first')
        self.hwnd, self.title, self.rect = hit
        if self.rect[0] <= -30000:          # minimised: restore, don't click
            ptwin.raise_window(self.hwnd)
        if self.rect[2] - self.rect[0] < 1700:
            ptwin.maximize(self.hwnd)
        self.hwnd, self.title, self.rect = ptwin.find(title, include_minimized=True)
        ptwin.raise_window(self.hwnd)

    # ------------------------------------------------------------------ geometry
    @property
    def l(self):
        return self.rect[0]

    @property
    def b(self):
        return self.rect[3]

    def pal(self, dx, dy):
        """Palette point from bottom-left of the main window."""
        return (self.l + dx, self.b - dy)

    # ------------------------------------------------------------------ focus
    def front(self, hwnd=None, tries=3):
        """Make sure the window we are about to drive owns the foreground.

        Without this, a click meant for PT lands in whatever window the human
        brought forward - and the run "passes" while doing nothing.
        """
        hwnd = hwnd or self.hwnd
        for _ in range(tries):
            if ptwin.foreground() == hwnd:
                return True
            ptwin.raise_window(hwnd)
            time.sleep(0.3)
        raise PtError('window %s does not hold the foreground - hands off the '
                      'desktop or click into Packet Tracer first' % hwnd)

    # ------------------------------------------------------------------ palette
    def _filter(self, text):
        x, y = self.pal(PAL_FILTER_DX, PAL_FILTER_DY)
        ptwin.click(x, y, 0.25)
        ptwin.combo(ptwin.VK_CONTROL, 0x41)      # Ctrl+A
        ptwin.key(ptwin.VK_DELETE, 0.15)
        time.sleep(0.25)
        if text:
            ptwin.clip_set(text)
            time.sleep(0.15)
            ptwin.combo(ptwin.VK_CONTROL, 0x56)  # Ctrl+V into the filter box
            time.sleep(0.35)
            ptwin.key(ptwin.VK_RETURN, 0.5)
        time.sleep(0.7)

    def _palette_icons(self):
        """Icon centres in the model row: pure-PIL column scan for blue pixels."""
        band_y0 = self.b - PAL_ROW_DY - 17
        band_y1 = self.b - PAL_ROW_DY + 17
        img = ptwin.shot('_ptlab_palette.png', box=(0, band_y0, 800, band_y1))
        px = img.load()
        w, h = img.size
        runs, start = [], None
        # x < 210 is the device-type column (Network Devices / End Devices / ...),
        # which sits in the same y band and used to be mistaken for a model icon
        for x in range(210, w):
            n = 0
            for y in range(h):
                r, g, b = px[x, y][:3]
                if b > 120 and b - r > 8:
                    n += 1
            if n >= 2 and start is None:
                start = x
            elif n < 2 and start is not None:
                runs.append((start, x))
                start = None
        if start is not None:
            runs.append((start, w))
        return [((a + b2) // 2, band_y0 + (band_y1 - band_y0) // 2)
                for a, b2 in runs if b2 - a >= 22]

    def place(self, model, x, y):
        """Put a device model on the canvas; returns the click point."""
        self.front()
        self._filter(model)
        icons = self._palette_icons()
        if len(icons) > 8:
            # the clipboard paste did not reach the filter box - type it
            self._filter('')
            ptwin._type_ascii(model, 0.05)
            ptwin.key(ptwin.VK_RETURN, 0.5)
            time.sleep(0.7)
            icons = self._palette_icons()
        if not icons:
            raise PtError('no palette icon for %r - check the model name' % model)
        ix, iy = icons[0]
        ptwin.drag(ix, iy, x, y, steps=26, delay=0.8)
        time.sleep(0.4)
        return (x, y)

    def connect(self, a, b, cable='straight',
                a_offset=(82, 86), b_offset=(42, 38)):
        """Cable two canvas points.  Offsets are the port-menu item clicks that
        the caller has verified (see ``probe_ports`` when unsure)."""
        self.front()
        cx, cy = self.pal(*CAT_CONNECTIONS)
        ptwin.click(cx, cy, 0.4)
        time.sleep(0.3)
        idx = CABLES[cable]
        ptwin.click(self.l + PAL_ICON_X0 + PAL_ICON_PITCH * idx,
                    self.b - PAL_ROW_DY, 0.4)
        time.sleep(0.3)
        ptwin.click(a[0], a[1], 0.8)
        time.sleep(0.9)
        ptwin.click(a[0] + a_offset[0], a[1] + a_offset[1], 0.7)
        time.sleep(0.5)
        ptwin.click(b[0], b[1], 0.8)
        time.sleep(0.9)
        ptwin.click(b[0] + b_offset[0], b[1] + b_offset[1], 0.8)
        time.sleep(0.7)

    # ------------------------------------------------------------------ devices
    def open(self, point, title=None, timeout=6.0):
        """Double-click a device and return its window handle.

        The cable tool stays armed after a connection and swallows the next
        click, so drop it with Esc first and retry the double-click a few times.
        """
        self.front()
        deadline = time.time() + timeout
        while time.time() < deadline:
            ptwin.key(ptwin.VK_ESCAPE, 0.25)
            ptwin.key(ptwin.VK_ESCAPE, 0.25)
            ptwin.dclick(point[0], point[1], 0.9)
            for _ in range(12):
                time.sleep(0.3)
                hit = self._device_window(title)
                if hit:
                    ptwin.raise_window(hit[0])
                    return hit[0]
        raise PtError('device window did not open (is the cable tool stuck?)')

    @staticmethod
    def _device_window(title=None):
        names = ('Router0', 'Router1', 'Router2', 'Switch0', 'Switch1',
                 'Switch2', 'PC0', 'PC1', 'PC2')
        for h, t, r in ptwin.windows():
            if title:
                if t == title or t.startswith(title):
                    return h, t, r
            elif t in names:
                return h, t, r
        return None

    def cli(self, hwnd):
        """Activate the CLI tab, maximise the window, return the terminal text.

        Maximising matters: the read-back only sees the visible page, and a
        2950 `show interfaces status` is 25 lines long.
        """
        self.front(hwnd)
        self.maximize_device(hwnd)
        for dx, dy in ((179, 60), (165, 59), (193, 60)):
            r = ptwin.rect(hwnd)
            ptwin.click(r[0] + dx, r[1] + dy, 0.6)
            time.sleep(0.5)
            text = self.terminal(hwnd)
            if text is not None:
                return text
        raise PtError('CLI tab not found in the device window')

    # ------------------------------------------------------------------ terminal
    # The Copy / Paste buttons hug the right edge of the CLI widget, but their
    # distance from the window border changes with the window size (a maximised
    # window and the 720px-wide default give different offsets).  So: try a few
    # candidates and let the clipboard tell us which one was right.
    def _copy_points(self, hwnd):
        l, t, r, b = ptwin.rect(hwnd)
        wide = (r - l) > 1700
        pts = [(r - 424, b - 86), (r - 344, b - 87)] if wide else \
              [(r - 189, b - 94), (r - 200, b - 94)]
        # a miss that lands in the text area clears the selection, so the
        # layout-correct point has to be tried first
        pts += [(r - 189, b - 94), (r - 424, b - 86), (r - 260, b - 94)]
        return pts

    def _paste_points(self, hwnd):
        l, t, r, b = ptwin.rect(hwnd)
        wide = (r - l) > 1700
        pts = [(r - 74, b - 86), (r - 71, b - 87)] if wide else \
              [(r - 89, b - 94), (r - 96, b - 94)]
        pts += [(r - 89, b - 94), (r - 71, b - 87)]
        return pts

    def terminal(self, hwnd, select=True):
        """Copy the visible CLI text out of the terminal.

        PT's Copy button is *disabled until something is selected*, so the
        selection has to be made first - a slow drag across the text area.
        (Ctrl+A / Ctrl+C do nothing here, and a fast drag selects nothing.)
        """
        self.front(hwnd)
        l, t, r, b = ptwin.rect(hwnd)
        if select:
            time.sleep(0.3)                      # let any overlay toolbar go
            ptwin.click(l + int((r - l) * 0.45), t + int((b - t) * 0.55), 0.3)
            time.sleep(0.25)
            ptwin.drag(l + 100, t + 150, r - 70, b - 118, steps=45, delay=0.9)
            time.sleep(0.35)
        for cx, cy in self._copy_points(hwnd):
            ptwin.clip_set(PROBE)
            ptwin.click(cx, cy, 0.35)
            time.sleep(0.35)
            got = ptwin.clip_get()
            if got not in (PROBE, ''):
                return got
        return None

    def maximize_device(self, hwnd):
        """Maximise a device window: more visible CLI lines to read at once."""
        l, t, r, b = ptwin.rect(hwnd)
        if r - l < 1700:
            ptwin.maximize(hwnd)
            time.sleep(0.8)
        return hwnd

    def _paste(self, hwnd, text, index=0):
        if not text.endswith('\n'):
            text += '\n'
        ptwin.clip_set(text)
        time.sleep(0.2)
        px, py = self._paste_points(hwnd)[index % len(self._paste_points(hwnd))]
        ptwin.click(px, py, 0.7)
        time.sleep(0.6)

    def _focus_terminal(self, hwnd):
        l, t, r, b = ptwin.rect(hwnd)
        ptwin.click(l + int((r - l) * 0.35), t + int((b - t) * 0.45), 0.25)
        time.sleep(0.2)

    prompt = staticmethod(parse_prompt)

    def wait_prompt(self, hwnd, timeout=25.0):
        """Block until the CLI shows a prompt again; returns the full text."""
        deadline = time.time() + timeout
        text = ''
        while time.time() < deadline:
            text = self.terminal(hwnd) or ''
            if '--More--' in text:
                self._focus_terminal(hwnd)
                ptwin.key(ptwin.VK_SPACE, 0.6)
                continue
            if self.prompt(text):
                return text
            time.sleep(0.8)
        raise PtError('no prompt after %.0fs; last line: %r'
                      % (timeout, (text or '').splitlines()[-1:] or ''))

    def _settle(self, hwnd, timeout=30.0):
        """Drive the console to a real prompt before pasting anything.

        A fresh device sits on "Press RETURN to get started!" (or on the
        initial-configuration question); pasting into that state eats the first
        command and the rest runs in user EXEC mode.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            t = self.terminal(hwnd) or ''
            if 'initial configuration dialog' in t:
                self._paste(hwnd, 'no')
                time.sleep(1.2)
                continue
            if 'Press RETURN to get started!' in t:
                self._focus_terminal(hwnd)
                ptwin.key(ptwin.VK_RETURN, 0.5)
                time.sleep(1.0)
                continue
            if '--More--' in t:
                self._focus_terminal(hwnd)
                ptwin.key(ptwin.VK_SPACE, 0.5)
                continue
            if self.prompt(t):
                return t
            time.sleep(0.8)
        raise PtError('console never reached a prompt')

    def paste(self, text, hwnd=None, timeout=25.0):
        """Paste IOS commands and wait for the prompt to come back.

        Handles the states that used to eat the first line: the press-RETURN
        banner, the initial-configuration dialog, and user EXEC mode.
        """
        hwnd = hwnd or self._active_device()
        time.sleep(0.4)
        cur = self._settle(hwnd)
        if self.prompt(cur)[2] == '>':
            self._paste(hwnd, 'enable')
            time.sleep(1.2)
            cur = self._settle(hwnd)
            if self.prompt(cur)[2] == '>':
                raise PtError('still in user EXEC after enable')
        first = text.strip().splitlines()[0].split()[0]
        last = None
        for idx in range(2):                      # 2nd try: other Paste offset
            self._paste(hwnd, text, idx)
            deadline = time.time() + timeout
            while time.time() < deadline:
                out = self.terminal(hwnd) or ''
                if '--More--' in out:
                    self._focus_terminal(hwnd)
                    ptwin.key(ptwin.VK_SPACE, 0.5)
                    continue
                # the echo of the command must be on screen: without this the
                # prompt from *before* the paste is mistaken for "done"
                if first in out and self.prompt(out):
                    for marker in ERR_MARKERS:
                        if marker in out:
                            raise PtError('CLI rejected input (%s):\n%s'
                                          % (marker.strip(), out[-600:]))
                    return out
                time.sleep(0.5)
            last = PtError('no echo of %r after %.0fs' % (first, timeout))
        raise last

    def _active_device(self):
        for h, t, r in ptwin.windows():
            if t in ('Router0', 'Router1', 'Router2', 'Switch0', 'Switch1',
                     'Switch2', 'PC0', 'PC1', 'PC2'):
                return h
        raise PtError('no device window open')

    # ------------------------------------------------------------------ verify
    def ports(self, switch_hwnd):
        """[(port, status)] from show interfaces status, connected ones first."""
        return parse_ports(self.paste('show interfaces status', switch_hwnd, timeout=30))

    # ------------------------------------------------------------------ file
    def new_file(self, allow_discard=False):
        """Ctrl+N to a blank canvas.  Refuses to discard unsaved work."""
        self.front()
        ptwin.combo(ptwin.VK_CONTROL, 0x4E)
        time.sleep(1.6)
        for h, t, r in ptwin.windows():
            if t.startswith('New --') or 'unsaved changes' in t:
                if not allow_discard:
                    ptwin.raise_window(h)
                    ptwin.key(ptwin.VK_ESCAPE, 0.5)
                    raise PtError('PT has unsaved changes - save first, '
                                  'or call new_file(allow_discard=True)')
                # "No" = discard (Yes / No / Cancel sit at 40% / 70% / 88%)
                ptwin.raise_window(h)
                ptwin.click(r[0] + int((r[2] - r[0]) * 0.70), r[3] - 37, 0.8)
                time.sleep(1.0)
        time.sleep(0.8)
