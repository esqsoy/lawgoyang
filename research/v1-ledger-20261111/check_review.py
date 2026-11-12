"""검토 결과(review.jsonl)를 점검하고, 두 검토(예: 서로 다른 모델)를 비교한다.

usage:
  python3 -I check_review.py <mapping 폴더> <review.jsonl>            # 점검: 열쇠가 매핑 줄과 맞나, '확인 필요' 줄을 다 다뤘나
  python3 -I check_review.py <mapping 폴더> <review A> <review B>     # 비교: 확신도 일치율, flag 겹침
"""
import json
import sys
from collections import Counter
from pathlib import Path

cur_of = lambda x: (str(x['current'].get('article') or ''), str(x['current'].get('para') or '')) if not str(x.get('article') or '') and isinstance(x.get('current'), dict) else ('', '')
key = lambda x: (x['year'], x['part'], str(x['q']), str(x['sub']), x['law'], str(x.get('article') or ''), str(x.get('para') or ''), cur_of(x))  # 조 칸이 빈 줄은 current로 가른다


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


folder = Path(sys.argv[1])
rows = load(folder / 'mapping.jsonl')
todo = {key(r) for r in rows if r['basis'] != '문제지 발췌' and r['confidence'] != '확실'}
allk = {key(r) for r in rows}


def check(path):
    rv = load(path)
    ks = [key(x) for x in rv]
    bad = [k for k in ks if k not in allk]
    dup = [k for k, n in Counter(ks).items() if n > 1]
    miss = todo - set(ks)
    conf = Counter(x.get('confidence') for x in rv if key(x) in todo)
    flags = [x for x in rv if x.get('flag')]
    nowhy = sum(1 for x in rv if not x.get('why'))
    print(f'{path}: {len(rv)}줄 | 확인 필요 대상 {len(todo)} 가운데 다룸 {len(todo & set(ks))}, 빠짐 {len(miss)}'
          f' | 열쇠 안 맞음 {len(bad)}, 겹침 {len(dup)}, 이유 없음 {nowhy}')
    print(f'   대상 줄 판정: {dict(conf)} | flag {len(flags)}')
    for k in list(bad)[:5]:
        print('   ! 안 맞는 열쇠', k)
    for k in list(miss)[:5]:
        print('   ! 빠진 줄', k)
    return {key(x): x for x in rv}


a = check(sys.argv[2])
if len(sys.argv) > 3:
    b = check(sys.argv[3])
    common = todo & set(a) & set(b)
    same = sum(1 for k in common if a[k]['confidence'] == b[k]['confidence'])
    up_a = {k for k in common if a[k]['confidence'] == '확실'}
    up_b = {k for k in common if b[k]['confidence'] == '확실'}
    fa = {k for k in a if a[k].get('flag')}
    fb = {k for k in b if b[k].get('flag')}
    print(f'\n비교(대상 {len(common)}줄): 확신도 일치 {same} ({same * 100 // max(1, len(common))}%)')
    print(f'   확실로 올림: A {len(up_a)}, B {len(up_b)}, 둘 다 {len(up_a & up_b)}')
    print(f'   flag: A {len(fa)}, B {len(fb)}, 둘 다 {len(fa & fb)}')
    for k in sorted(common, key=lambda k: (k[0], k[2], k[3])):
        if a[k]['confidence'] != b[k]['confidence']:
            print(f"   ≠ {k[0]} {k[2]}-{k[3]} {k[4]} {k[5]}조{('①②③④⑤⑥⑦⑧⑨⑩'[int(k[6]) - 1]) if k[6].isdigit() and 0 < int(k[6]) <= 10 else ''}"
                  f" | A {a[k]['confidence']}: {a[k].get('why', '')} | B {b[k]['confidence']}: {b[k].get('why', '')}")
    for k in sorted(fa | fb):
        print(f"   flag {k[0]} {k[2]}-{k[3]} {k[4]} {k[5]} | A {a.get(k, {}).get('fix', '-') if k in fa else '-'} | B {b.get(k, {}).get('fix', '-') if k in fb else '-'}")
