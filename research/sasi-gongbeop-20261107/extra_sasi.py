"""Diagnostics for analyze_sasi.py: long-gap hits, era decomposition, cliff test, marginal rule.

Usage: python3 -I extra_sasi.py SASI_MAPPING SASI_SUBQ PILOT_MAPPING OUT.md
Imports the year-set logic by exec of analyze_sasi.py's helpers is avoided; logic is duplicated minimally.
"""
import collections
import json
import math
import sys

SASI = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
SUBQ = [json.loads(l) for l in open(sys.argv[2], encoding='utf-8')]
PILOT = [json.loads(l) for l in open(sys.argv[3], encoding='utf-8')]
OUT = open(sys.argv[4], 'w', encoding='utf-8')
QTYPE = {(s['year'], s['part'], s['q'], s['sub']): s['qtype'] for s in SUBQ}
Y0, Y1 = 2002, 2026
YEARS = list(range(Y0, Y1 + 1))


def p(*a):
    print(*a, file=OUT)


def key(r):
    law, art = r['law'], r['article']
    cur = r.get('current')
    if cur == '없음':
        law += '(현행 없음)'
    elif isinstance(cur, dict):
        law = cur.get('law', law)
        art = cur['article'] if cur['article'] != '확인 필요' else '?' + r['article']
    return (law, art)


def sets_for(conf='all', src='both'):
    S = {y: set() for y in YEARS}
    src_of = collections.defaultdict(set)  # (year, key) -> {'사시','변시'}
    for r in SASI + PILOT:
        sasi = r['part'].startswith('사시')
        if src == 'sasi' and not sasi or src == 'bs' and sasi:
            continue
        if r['basis'] == '문제지 발췌' or r['article'] == '':
            continue
        if conf == 'sure' and r['confidence'] != '확실':
            continue
        if sasi and QTYPE[(r['year'], r['part'], r['q'], r['sub'])] == '이론':
            continue
        k = key(r)
        S[r['year']].add(k)
        src_of[(r['year'], k)].add('사시' if sasi else '변시')
    return S, src_of


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pc(x):
    return '–' if x != x else f'{100 * x:.1f}%'


def exposures(S):
    ex, last = [], {}
    for Y in YEARS:
        if Y > Y0:
            for k, ly in last.items():
                ex.append((k, ly, Y, Y - ly, k in S[Y]))
        for k in S[Y]:
            last[k] = Y
    return ex


def era(y):
    return '사시만(2002~11)' if y <= 2011 else ('합집합(2012~17)' if y <= 2017 else '변시만(2018~)')


def fisher_two_sided(a, b, c, d):
    """2x2 [[a,b],[c,d]] exact test (hypergeometric), two-sided by probability <= observed."""
    n1, n2, m1 = a + b, c + d, a + c
    N = n1 + n2

    def lc(n, k):
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

    def prob(x):
        return math.exp(lc(n1, x) + lc(n2, m1 - x) - lc(N, m1))
    p0 = prob(a)
    lo, hi = max(0, m1 - n2), min(n1, m1)
    return sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p0 * (1 + 1e-9))


S, SRC = sets_for()
EX = exposures(S)

p('# 보조 진단 (자동 생성)')
p()
p('## A. 마지막 출제 후 7년 이상 지나 다시 나온 조문 (주 결과 정의)')
p()
p('| g | 조문 | 직전 출제(시험) | 다시 나온 해(시험) |')
p('|---|---|---|---|')
for k, ly, Y, g, h in sorted(EX, key=lambda e: (-e[3], e[2])):
    if h and g >= 7:
        p(f'| {g} | {k[0]} {k[1]}조 | {ly} ({"+".join(sorted(SRC[(ly, k)]))}) | {Y} ({"+".join(sorted(SRC[(Y, k)]))}) |')
p()

p('## B. 직전 출제 시기 × 목표 시기별 h(g)')
p()
p('직전 출제 해의 시험 체제(사시만 / 두 시험 합집합 / 변시만)와 목표 연도 체제로 나눈다. 칸 = 재출제/위험 (비율).')
p()
bands = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 18), (19, 24)]
cell = collections.defaultdict(lambda: [0, 0])
for k, ly, Y, g, h in EX:
    for a, b in bands:
        if a <= g <= b:
            c = cell[(era(ly), era(Y), (a, b))]
            c[0] += h
            c[1] += 1
combos = sorted({(e1, e2) for (e1, e2, _) in cell})
p('| 직전 → 목표 | ' + ' | '.join(f'{a}~{b}' for a, b in bands) + ' |')
p('|---|' + '---|' * len(bands))
for e1, e2 in combos:
    cells = []
    for bd in bands:
        h, r = cell[(e1, e2, bd)]
        cells.append(f'{h}/{r} ({pc(h / r)})' if r else '')
    p(f'| {e1} → {e2} | ' + ' | '.join(cells) + ' |')
p()

p('## C. 7~10년과 11~14년의 차이 검정 (Fisher 정확검정, 양측)')
p()
for nm, filt in [('목표 2003~2026 전체', lambda Y: True), ('목표 2018~2026', lambda Y: Y >= 2018),
                 ('목표 2003~2017', lambda Y: Y <= 2017)]:
    a = sum(h for k, ly, Y, g, h in EX if filt(Y) and 7 <= g <= 10)
    n1 = sum(1 for k, ly, Y, g, h in EX if filt(Y) and 7 <= g <= 10)
    c = sum(h for k, ly, Y, g, h in EX if filt(Y) and 11 <= g <= 14)
    n2 = sum(1 for k, ly, Y, g, h in EX if filt(Y) and 11 <= g <= 14)
    pv = fisher_two_sided(a, n1 - a, c, n2 - c)
    p(f'- {nm}: 7~10년 {a}/{n1} = {pc(a / n1)} vs 11~14년 {c}/{n2} = {pc(c / n2 if n2 else float("nan"))}, p = {pv:.4f}')
# same for 5~6 vs 7~10 (plateau test)
for nm, filt in [('목표 2003~2026 전체', lambda Y: True), ('목표 2018~2026', lambda Y: Y >= 2018)]:
    a = sum(h for k, ly, Y, g, h in EX if filt(Y) and 3 <= g <= 6)
    n1 = sum(1 for k, ly, Y, g, h in EX if filt(Y) and 3 <= g <= 6)
    c = sum(h for k, ly, Y, g, h in EX if filt(Y) and 7 <= g <= 10)
    n2 = sum(1 for k, ly, Y, g, h in EX if filt(Y) and 7 <= g <= 10)
    pv = fisher_two_sided(a, n1 - a, c, n2 - c)
    p(f'- (평탄 구간 확인) {nm}: 3~6년 {a}/{n1} = {pc(a / n1)} vs 7~10년 {c}/{n2} = {pc(c / n2)}, p = {pv:.4f}')
p()

p('## D. 직전 출제가 2012년 이후(변시 시작 후)인 조문만')
p()
p('목표 연도가 2018년 이후이고 직전 출제가 2012년 이후인 노출만 센다(체제 차이를 줄인 비교). g는 최대 14.')
p()
p('| g 묶음 | 재출제/위험 | h | 95% Wilson |')
p('|---|---|---|---|')
for a, b in [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 14)]:
    h = sum(e[4] for e in EX if e[1] >= 2012 and e[2] >= 2018 and a <= e[3] <= b)
    r = sum(1 for e in EX if e[1] >= 2012 and e[2] >= 2018 and a <= e[3] <= b)
    l, u = wilson(h, r)
    p(f'| {a}~{b} | {h}/{r} | {pc(h / r if r else float("nan"))} | {pc(l)}–{pc(u)} |')
p()


def pool(S, Y, n):
    out = set()
    for t in range(max(Y0, Y - n), Y):
        out |= S[t]
    return out


p('## E. 창 곡선의 한계 효율 잣대')
p()
p('기준 = N=1~5 풀이 낸 적중을 풀 크기 합으로 나눈 값(풀 조문 10개당 적중). 잣대 = 늘어난 조문 10개당 적중이 그 절반 이상인 마지막 N. 한 해씩은 들쭉날쭉하니 3년 묶음(6~8, 9~11, 12~14, 15~17, 18~20)으로도 본다.')
p()
for nm, targets, conf in [('목표 2022~2026, 주 결과', range(2022, 2027), 'all'),
                          ('목표 2022~2026, 확실만', range(2022, 2027), 'sure'),
                          ('목표 2017~2026(N≤15), 주 결과', range(2017, 2027), 'all'),
                          ('목표 2017~2026(N≤15), 확실만', range(2017, 2027), 'sure')]:
    SS = S if conf == 'all' else sets_for('sure')[0]
    targets = list(targets)
    nmax = 20 if targets[0] == 2022 else 15
    H = {n: sum(len(SS[Y] & pool(SS, Y, n)) for Y in targets) for n in range(0, nmax + 1)}
    P = {n: sum(len(pool(SS, Y, n)) for Y in targets) for n in range(0, nmax + 1)}
    base = 10 * H[5] / P[5]
    p(f'**{nm}**: N=5 풀 10개당 적중 {base:.2f}, 절반 {base / 2:.2f}')
    p()
    p('| N 구간 | +적중 | +풀(연평균) | 10개당 적중 | 기준 대비 |')
    p('|---|---|---|---|---|')
    last_ok = None
    for n in range(6, nmax + 1):
        dH, dP = H[n] - H[n - 1], P[n] - P[n - 1]
        e = 10 * dH / dP if dP else float('nan')
        if e >= base / 2:
            last_ok = n
    blocks = [(6, 8), (9, 11), (12, 14), (15, 17), (18, 20)]
    for a, b in blocks:
        if b > nmax:
            continue
        dH, dP = H[b] - H[a - 1], P[b] - P[a - 1]
        e = 10 * dH / dP
        p(f'| {a}~{b} | {dH} | {dP / len(targets):.1f} | {e:.2f} | {e / base:.0%} |')
    p()
    p(f'- 참고: 한 해 단위로 본 마지막 N은 {last_ok}이지만, 끝자락 한 해의 1건(작은 풀)에 좌우되므로 3년 묶음을 본다.')
    p()

p('## F. 2022~2026에서 N을 늘려야만 잡히는 조문')
p()
p('| 목표 연도 | 조문 | 직전 출제 | 필요한 최소 N |')
p('|---|---|---|---|')
for Y in range(2022, 2027):
    for k in sorted(S[Y]):
        prev = [t for t in range(Y0, Y) if k in S[t]]
        if prev and Y - max(prev) >= 6:
            p(f'| {Y} | {k[0]} {k[1]}조 | {max(prev)} | {Y - max(prev)} |')
p()
OUT.close()
print('ok')
