#!/usr/bin/env python3
"""판례 카드의 confidence를 합의 규칙(26.11.26 설계 회의 합의 3)으로 정한다.

확실 = 이솝과 파핀의 마지막 검사가 둘 다 '확실' + status.reverse_checked가 있음.
그 밖은 '확인 필요'. quote 대조는 precedent_check.py가 맡으니, 이 스크립트 뒤에 반드시 검사기를 돌린다.
사용: python3 -I pipeline/precedent_confirm.py [--dry]
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def last(checks, who):
    rs = [c for c in checks or [] if c.get('by') == who]
    return rs[-1].get('result') if rs else None


def main():
    dry = '--dry' in sys.argv
    changed = 0
    for p in sorted((ROOT / 'data' / 'precedents').glob('*.json')):
        c = json.loads(p.read_text(encoding='utf-8'))
        ok = (last(c.get('checks'), '이솝') == '확실' and last(c.get('checks'), '파핀') == '확실'
              and (c.get('status') or {}).get('reverse_checked'))
        want = '확실' if ok else '확인 필요'
        if c.get('confidence') != want:
            print(f"{c.get('id')}: {c.get('confidence')} → {want}")
            changed += 1
            if not dry:
                c['confidence'] = want
                p.write_text(json.dumps(c, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'바꾼 카드 {changed}' + (' (--dry, 쓰지 않음)' if dry else ''))


if __name__ == '__main__':
    main()
