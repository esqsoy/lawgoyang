"""Minimal HWP 5.0 text extractor (BodyText/SectionN -> PARA_TEXT records).

Usage: python3 -I hwp2txt.py IN.hwp OUT.txt
Treats input as untrusted: only reads OLE streams, never executes anything.
"""
import struct
import sys
import zlib

import olefile

HWPTAG_BEGIN = 0x10
HWPTAG_PARA_HEADER = HWPTAG_BEGIN + 50
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51

# control chars occupying 8 WCHARs (16 bytes) in PARA_TEXT
EXT_CTRL = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}
INL_CTRL = {4, 5, 6, 7, 8, 19, 20}


def para_text(data):
    out = []
    i = 0
    n = len(data)
    while i + 1 < n:
        ch = struct.unpack_from('<H', data, i)[0]
        if ch < 32:
            if ch in EXT_CTRL or ch in INL_CTRL:
                i += 16
                continue
            if ch == 9:
                out.append('\t')
                i += 16
                continue
            if ch in (10, 13):
                out.append('\n')
            elif ch == 24:
                out.append('-')
            elif ch in (30, 31):
                out.append(' ')
            i += 2
            continue
        out.append(chr(ch))
        i += 2
    return ''.join(out)


def records(buf):
    i = 0
    n = len(buf)
    while i + 4 <= n:
        hdr = struct.unpack_from('<I', buf, i)[0]
        tag = hdr & 0x3FF
        level = (hdr >> 10) & 0x3FF
        size = (hdr >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            size = struct.unpack_from('<I', buf, i)[0]
            i += 4
        yield tag, level, buf[i:i + size]
        i += size


def main(src, dst):
    ole = olefile.OleFileIO(src)
    fh = ole.openstream('FileHeader').read()
    flags = struct.unpack_from('<I', fh, 36)[0]
    compressed = bool(flags & 1)
    if flags & 2:
        raise SystemExit('password-protected HWP')
    if flags & 4:
        raise SystemExit('distribution (ViewText) HWP not supported')
    secs = sorted(
        [e for e in ole.listdir() if e[0] == 'BodyText'],
        key=lambda e: int(e[1].replace('Section', '')),
    )
    lines = []
    for e in secs:
        raw = ole.openstream(e).read()
        buf = zlib.decompress(raw, -15) if compressed else raw
        for tag, level, data in records(buf):
            if tag == HWPTAG_PARA_TEXT:
                lines.append(para_text(data).rstrip('\n'))
            elif tag == HWPTAG_PARA_HEADER:
                pass
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
