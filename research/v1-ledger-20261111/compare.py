"""원장 v0과 v1을 비교한다: 새로 외울 조문, 보관함에서 돌아온 조문, 시험별·법령별 수, 빈출도 상위.

usage: python3 -I compare.py <ledger-v0.json> <ledger-v1.json> <out.md>
"""
import json
import sys
from collections import Counter, defaultdict

v0 = json.load(open(sys.argv[1], encoding='utf-8'))
v1 = json.load(open(sys.argv[2], encoding='utf-8'))
out = open(sys.argv[3], 'w', encoding='utf-8')

key = lambda a: (a['law'], a['article'])
a0 = {key(a): a for a in v0['articles']}
b0 = {key(a): a for a in v0['archive']}
a1 = {key(a): a for a in v1['articles']}
b1 = {key(a): a for a in v1['archive']}
new = [a1[k] for k in a1 if k not in a0 and k not in b0]
back = [a1[k] for k in a1 if k in b0]
total = lambda a: sum(a['freq'].values())
OLD = set(v0['exams'])


def w(s=''):
    out.write(s + '\n')


def label(a):
    return f"{a['law']} 제{a['article']}조"


w('# 원장 v0 → v1 비교 (2026-11-11)')
w()
w(f"창 {v1['window'][0]}~{v1['window'][1]}. 빈출도는 시험별 회차 수(창 안). 발췌 조문·이론 설문은 뺐다.")
w()
w('| | v0 | v1 |')
w('|---|---|---|')
w(f"| 외울 조문 | {len(a0)} | {len(a1)} |")
w(f"| 보관함 | {len(b0)} | {len(b1)} |")
w(f"| 원장 밖(현행 없음) 줄 | {v0['counts']['retired_rows']} | {v1['counts']['retired_rows']} |")
w()
w(f"- 새로 들어온 조문(v0에 없던 조): **{len(new)}**")
w(f"- 보관함에서 외울 조문으로 돌아온 조문: **{len(back)}**")
w(f"- v0 외울 조문 가운데 새 시험에도 나온 조문: **{sum(1 for k in a0 if k in a1 and set(a1[k]['freq']) - OLD)}**")
w()

w('## 시험별 기여 (창 안 hit가 있는 외울 조문 수)')
w()
w('| 시험 | 조문 수 | 그 시험에만 나온 조문 |')
w('|---|---|---|')
for e, name in v1['exams'].items():
    n = sum(1 for a in a1.values() if e in a['freq'])
    only = sum(1 for a in a1.values() if set(a['freq']) == {e})
    w(f'| {e} {name} | {n} | {only} |')
w()

w('## 법령별 외울 조문 수')
w()
c0 = Counter(a['law'] for a in a0.values())
c1 = Counter(a['law'] for a in a1.values())
w('| 법령 | v0 | v1 | 늘어남 |')
w('|---|---|---|---|')
for law, n in c1.most_common():
    w(f'| {law} | {c0.get(law, 0)} | {n} | {n - c0.get(law, 0):+d} |')
w()

w('## 새로 들어온 조문 (빈출도 순)')
w()
w('| 조문 | 빈출도 | 확인 필요 |')
w('|---|---|---|')
for a in sorted(new, key=lambda a: (-total(a), a['law'], a['article'])):
    w(f"| {label(a)} | {a['freq_text']} | {'예' if a['needs_check'] else ''} |")
w()

w('## 보관함에서 돌아온 조문')
w()
w('| 조문 | v1 빈출도 | v0 마지막 출제 |')
w('|---|---|---|')
for a in sorted(back, key=lambda a: (-total(a), a['law'], a['article'])):
    w(f"| {label(a)} | {a['freq_text']} | {b0[key(a)]['last_year']} |")
w()

w('## v1 빈출도 상위 40')
w()
w('| 조문 | v1 빈출도 | v0 빈출도 |')
w('|---|---|---|')
for a in sorted(a1.values(), key=lambda a: (-total(a), a['law'], a['article']))[:40]:
    w(f"| {label(a)} | {a['freq_text']} | {a0[key(a)]['freq_text'] if key(a) in a0 else '(새)'} |")
out.close()
print(f'외울 {len(a0)}→{len(a1)}, 보관함 {len(b0)}→{len(b1)}, 새 {len(new)}, 돌아옴 {len(back)}')
