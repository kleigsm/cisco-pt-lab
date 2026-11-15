#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Capture a screen region, upscale it, and overlay a coordinate grid.

Why: Packet Tracer windows scroll and re-layout, so pixel positions read from a
plain screenshot go stale. Reading a grid-labelled crop right before clicking is
the reliable way to pick coordinates.

Usage:
    python grid_shot.py --box 0 880 1200 1040 --scale 2 --out grid.png
    python grid_shot.py --box 600 300 1300 800 --scale 1.5 --minor 20 --major 100

--box    left top right bottom in screen pixels (required)
--scale  upscale factor for easier reading (default 2)
--minor  minor grid step in ORIGINAL pixels (default 20)
--major  labelled grid step in ORIGINAL pixels (default 100)
--out    output path (default grid.png next to this script)
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageGrab


def parse_args(argv):
    ap = argparse.ArgumentParser(description='Grid-labelled crop of the screen.')
    ap.add_argument('--box', nargs=4, type=int, required=True,
                    metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'))
    ap.add_argument('--scale', type=float, default=2.0)
    ap.add_argument('--minor', type=int, default=20)
    ap.add_argument('--major', type=int, default=100)
    ap.add_argument('--out', default='grid.png')
    return ap.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    x0, y0, x1, y1 = args.box
    if x1 <= x0 or y1 <= y0:
        print('error: --box must be left<right and top<bottom', file=sys.stderr)
        return 2

    shot = ImageGrab.grab()
    crop = shot.crop((x0, y0, x1, y1))
    w = max(1, int(round(crop.width * args.scale)))
    h = max(1, int(round(crop.height * args.scale)))
    crop = crop.resize((w, h), Image.LANCZOS)

    draw = ImageDraw.Draw(crop)
    for x in range(x0, x1 + 1, max(1, args.minor)):
        cx = int(round((x - x0) * args.scale))
        major = (x % args.major == 0)
        draw.line([(cx, 0), (cx, crop.height)],
                  fill=(255, 0, 0) if major else (255, 215, 215), width=1)
        if major:
            draw.text((cx + 1, 1), str(x), fill=(255, 0, 0))
    for y in range(y0, y1 + 1, max(1, args.minor)):
        cy = int(round((y - y0) * args.scale))
        major = (y % args.major == 0)
        draw.line([(0, cy), (crop.width, cy)],
                  fill=(0, 0, 255) if major else (210, 210, 255), width=1)
        if major:
            draw.text((1, cy + 1), str(y), fill=(0, 0, 255))

    out = args.out
    if not os.path.isabs(out):
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), out)
    crop.save(out)
    print('saved: {} ({}x{})'.format(out, crop.width, crop.height))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
