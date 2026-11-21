#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke test for ptlab - two modes.

--offline   pure parsing checks, no desktop interaction (safe while you work)
(default)   live run in Packet Tracer: blank canvas -> 2950 -> PC -> cable ->
            read the port status back -> show version

The live run refuses to touch a canvas with unsaved changes; pass --discard to
start a blank file anyway (Ctrl+N never saves, so the .pkt on disk is untouched).
"""
import argparse
import sys
import time

from ptlab import Pt, PtError, parse_ports, parse_prompt
from ptlab.driver import CABLES

SHOW_STATUS = """Port      Name               Status       Vlan       Duplex  Speed Type
Fa0/1                        connected    1          auto    auto 10/100BaseTX
Fa0/2                        notconnect   1          auto    auto 10/100BaseTX
Fa0/3                        connected    1          auto    auto 10/100BaseTX
Fa0/24                       notconnect   1          auto    auto 10/100BaseTX
"""


def run_offline():
    steps = []

    def check(name, cond, detail=''):
        steps.append((name, bool(cond), detail))
        print('%-4s %-34s %s' % ('PASS' if cond else 'FAIL', name, detail))

    check('prompt: privileged', parse_prompt('R1#') == ('R1', '', '#'))
    check('prompt: config-if', parse_prompt('R1(config-if)#\n') == ('R1', '(config-if)', '#'))
    check('prompt: user mode', parse_prompt('Router>') == ('Router', '', '>'))
    check('prompt: ignores output lines',
          parse_prompt('Success rate is 80 percent\nR2#') == ('R2', '', '#'))
    check('prompt: paging is not a prompt', parse_prompt('Fa0/9 notconnect\n--More--') is None)

    ports = parse_ports(SHOW_STATUS)
    check('ports: parsed', len(ports) == 4, str(ports))
    check('ports: connected first', ports[0][1] == 'connected', ports[0])
    check('ports: names', [p for p, _ in ports][:2] == ['Fa0/1', 'Fa0/3'], str(ports[:2]))

    check('cable indexes', CABLES['straight'] == 2 and CABLES['cross'] == 3
          and CABLES['serial-dce'] == 7, str(CABLES))

    bad = [n for n, ok, _ in steps if not ok]
    print('\n%d/%d offline checks passed' % (len(steps) - len(bad), len(steps)))
    return 0 if not bad else 1


def run_live(args):
    t0 = time.time()
    steps = []

    def step(name, ok, detail=''):
        steps.append((name, ok, detail))
        print('%-4s %-28s %s' % ('PASS' if ok else 'FAIL', name, detail))

    pt = Pt()
    print('attached: %r  rect=%s' % (pt.title, pt.rect))

    if not args.keep:
        try:
            pt.new_file(allow_discard=args.discard)
            step('new blank file', True)
        except PtError as e:
            step('new blank file', False, str(e))
            return 2

    sw = pt.place('2950-24', 760, 300)
    step('place 2950-24', True, 'at %s' % (sw,))
    pc = pt.place('PC-PT', 380, 300)
    step('place PC-PT', True, 'at %s' % (pc,))

    pt.connect(pc, sw)
    step('cable pc-switch', True)

    hwnd = pt.open(sw, 'Switch0')
    step('open device window', True, 'hwnd=%s' % hwnd)

    text = pt.cli(hwnd)
    step('cli tab readable', True, '%d chars' % len(text))

    rows = pt.ports(hwnd)
    connected = [p for p, s in rows if s == 'connected']
    step('port shows connected', bool(connected), str(connected))

    ver = pt.paste('show version', hwnd)
    step('show version', 'Cisco Internetwork Operating System' in ver,
         ver.strip().splitlines()[-1][:48] if ver.strip() else '')

    bad = [n for n, ok, _ in steps if not ok]
    print('\n%d/%d passed in %.1fs' % (len(steps) - len(bad), len(steps), time.time() - t0))
    if bad:
        print('failed: %s' % ', '.join(bad))
        return 1
    print('PT now shows an unsaved blank lab; close it without saving.')
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline', action='store_true',
                    help='only run parsing checks, never touch the desktop')
    ap.add_argument('--discard', action='store_true',
                    help='discard unsaved changes when starting a blank file')
    ap.add_argument('--keep', action='store_true',
                    help='test on the current canvas instead of opening a new file')
    args = ap.parse_args(argv)
    return run_offline() if args.offline else run_live(args)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
