"""Backtest 5-year vs 10-year retention windows on mapping.jsonl.

Usage: python3 -I analyze.py mapping.jsonl OUT.md
"""
import collections
import json
import math
import sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
OUT = open(sys.argv[2], 'w', encoding='utf-8')
YEARS = list(range(2012, 2027))
MAIN = list(range(2022, 2027))
REF = list(range(2017, 2022))

# 설문 목록 (채점 단위로 묶은 것). key = (year, q, sub)
SUBQ = {
    2012: [('1', '1'), ('1', '2'), ('1', '3'), ('2', '1'), ('2', '2'), ('2', '3(1)'), ('2', '3(2)'), ('2', '3(3)'), ('2', '4')],
    2013: [('1', s) for s in '12345'] + [('2', '1'), ('2', '2(1)'), ('2', '2(2)'), ('2', '3(1)'), ('2', '3(2)')],
    2014: [('1', s) for s in '12345'] + [('2', '1(1)'), ('2', '1(2)'), ('2', '2'), ('2', '3(1)'), ('2', '3(2)'), ('2', '3(3)')],
    2015: [('1의1', '1'), ('1의1', '2'), ('1의1', '3'), ('1의2', ''), ('1의3', ''), ('2의1', '1가'), ('2의1', '1나'), ('2의1', '2'), ('2의1', '3'), ('2의2', '')],
    2016: [('1', s) for s in '1234'] + [('2', '1'), ('2', '2'), ('2', '3가'), ('2', '3나'), ('2', '3다'), ('2', '4가'), ('2', '4나')],
    2017: [('1', s) for s in '123'] + [('2', s) for s in '1234'],
    2018: [('1', '1'), ('1', '2'), ('1', '3'), ('1', '4(1)'), ('1', '4(2)')] + [('2', s) for s in '12345'],
    2019: [('1의1', ''), ('1의2', '1'), ('1의2', '2')] + [('2', s) for s in '1234'],
    2020: [('1의1', s) for s in '123'] + [('1의2', s) for s in '1234'] + [('2', '1'), ('2', '2'), ('2', '3'), ('2', '4-1'), ('2', '4-2'), ('2', '4-3')],
    2021: [('1의1', '1'), ('1의1', '2')] + [('1의2', s) for s in '1234'] + [('2', '1'), ('2', '2'), ('2', '3'), ('2', '4(1)'), ('2', '4(2)')],
    2022: [('1', '1'), ('1', '2(1)'), ('1', '2(2)'), ('1', '3'), ('1', '4(1)'), ('1', '4(2)')] + [('2', s) for s in '1234'],
    2023: [('1', s) for s in '123456'] + [('2', '1(1)'), ('2', '1(2)'), ('2', '2'), ('2', '3'), ('2', '4'), ('2', '5')],
    2024: [('1', '1'), ('1', '2'), ('1', '3'), ('1', '4(1)'), ('1', '4(2)')] + [('2', s) for s in '1234'],
    2025: [('1', '1'), ('1', '2(1)'), ('1', '2(2)'), ('1', '3(1)'), ('1', '3(2)'), ('2', '1(1)'), ('2', '1(2)'), ('2', '2'), ('2', '3'), ('2', '4')],
    2026: [('1의1', '1'), ('1의1', '2'), ('1의2', '1'), ('1의2', '2'), ('1의3', '1'), ('1의3', '2'), ('2', '1'), ('2', '2(1)'), ('2', '2(2)'), ('2', '3(1)'), ('2', '3(2)'), ('2', '4')],
}


def p(*a):
    print(*a, file=OUT)


def key(r, unit, normalize):
    art, para = r['article'], r['para']
    if normalize and 'current' in r:
        art, para = r['current']['article'], r['current']['para']
    if unit == '조':
        return (r['law'], art)
    return (r['law'], art, para)


def label(k):
    s = f'{k[0]} {k[1]}조'
    if len(k) == 3 and k[2]:
        s += f' {k[2]}항'
    return s


def year_sets(version='core', unit='조', normalize=True, conf='all'):
    sets = {y: set() for y in YEARS}
    for r in rows:
        if version == 'core' and r['basis'] == '문제지 발췌':
            continue
        if version == 'with_excerpt' and r['kind'] in ('자치법규', '행정규칙'):
            continue
        if conf == 'sure' and r['confidence'] != '확실':
            continue
        sets[r['year']].add(key(r, unit, normalize))
    return sets


def pool(sets, y, n):
    out = set()
    for t in range(max(2012, y - n), y):
        out |= sets[t]
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pct(x):
    return f'{100 * x:.0f}%'


def backtest(sets, years, show=True):
    tot = collections.Counter()
    extra_list = []
    lines = []
    for y in years:
        A = sets[y]
        p5, p10, pall = pool(sets, y, 5), pool(sets, y, 10), pool(sets, y, 99)
        h5, h10, hall = A & p5, A & p10, A & pall
        extra = h10 - h5
        w10 = f'{max(2012, y - 10)}–{y - 1}'
        lines.append(f'| {y} | {len(A)} | {len(h5)} ({pct(len(h5) / len(A))}) | {len(h10)} ({pct(len(h10) / len(A))}) | {len(hall)} ({pct(len(hall) / len(A))}) | {len(p5)} | {len(p10)} | {w10} | {len(extra)} |')
        tot.update(A=len(A), h5=len(h5), h10=len(h10), hall=len(hall), p5=len(p5), p10=len(p10), extra=len(extra))
        for k in sorted(extra):
            last = max(t for t in range(2012, y) if k in sets[t])
            extra_list.append((y, label(k), y - last))
    if show:
        p('| 목표 연도 Y | 출제 조문 수 |A_Y| | 5년 풀 적중 (recall5) | 10년 풀 적중 (recall10) | 전체 이력 적중 | 5년 풀 크기 | 10년 풀 크기 | 10년 창 | 10년 풀로만 추가 적중 |')
        p('|---|---|---|---|---|---|---|---|---|')
        for l in lines:
            p(l)
        n = tot['A']
        l5, u5 = wilson(tot['h5'], n)
        l10, u10 = wilson(tot['h10'], n)
        p(f"| **합계** | {n} | {tot['h5']} ({pct(tot['h5'] / n)}) | {tot['h10']} ({pct(tot['h10'] / n)}) | {tot['hall']} ({pct(tot['hall'] / n)}) | 평균 {tot['p5'] / len(years):.1f} | 평균 {tot['p10'] / len(years):.1f} | | {tot['extra']} |")
        p()
        p(f"- 합산 recall5 = {tot['h5']}/{n} = {pct(tot['h5'] / n)} (95% Wilson {pct(l5)}–{pct(u5)}), recall10 = {tot['h10']}/{n} = {pct(tot['h10'] / n)} (95% {pct(l10)}–{pct(u10)})")
        dp = (tot['p10'] - tot['p5']) / len(years)
        p(f"- 10년 창이 더 덮은 몫: {tot['extra']}/{n} = {pct(tot['extra'] / n)}p. 대신 풀은 해마다 평균 {dp:.1f}개(+{100 * dp / (tot['p5'] / len(years)):.0f}%) 늘어남.")
        if tot['p5']:
            p(f"- 풀 1개당 적중: 5년 풀 {tot['h5'] / tot['p5']:.3f}, 6~10년 구간에만 있는 조문 {tot['extra'] / max(1, tot['p10'] - tot['p5']):.3f}")
        p()
    return tot, extra_list


def gaps(sets):
    occ = collections.defaultdict(list)
    for y in YEARS:
        for k in sets[y]:
            occ[k].append(y)
    g = []
    for k, ys in occ.items():
        ys.sort()
        for a, b in zip(ys, ys[1:]):
            g.append((b - a, k, a, b))
    return occ, g


def since_last(sets, years):
    """For each article in A_Y that appeared before: years since last appearance."""
    out = []
    for y in years:
        for k in sets[y]:
            prev = [t for t in range(2012, y) if k in sets[t]]
            if prev:
                out.append((y - max(prev), y, k))
    return out


# ------------------------------------------------------------------ report
p('# 분석 출력 (자동 생성)')
p()
p(f'mapping 줄 수: {len(rows)}')
bc = collections.Counter((r['basis'], r['confidence']) for r in rows)
p('basis·confidence: ' + ', '.join(f'{a}/{b} {c}' for (a, b), c in sorted(bc.items())))
p()

# 설문 coverage
anch = set((r['year'], r['q'], r['sub']) for r in rows if r['basis'] != '문제지 발췌')
nsub = sum(len(v) for v in SUBQ.values())
none = [(y, q, s) for y, v in SUBQ.items() for q, s in v if (y, q, s) not in anch]
extra_keys = anch - set((y, q, s) for y, v in SUBQ.items() for q, s in v)
p(f'설문 수 {nsub}, 그중 발췌 외 조문이 1개 이상 매핑된 설문 {nsub - len(none)}, 근거 조문 없음(판례 법리·발췌 조문만) {len(none)}')
p('근거 조문 없는 설문: ' + ', '.join(f'{y} {q}-{s}' for y, q, s in none))
if extra_keys:
    p('SUBQ에 없는 키(점검용): ' + str(sorted(extra_keys)))
p()

configs = [
    ('core', '조', True, 'all', '발췌 제외 · 조 단위 · 현행 번호 정규화 · 전체 신뢰도 (주 결과)'),
    ('core', '항', True, 'all', '발췌 제외 · 항 단위'),
    ('core', '조', False, 'all', '발췌 제외 · 조 단위 · 출제 당시 번호(정규화 안 함)'),
    ('core', '조', True, 'sure', '발췌 제외 · 조 단위 · 확실만'),
    ('with_excerpt', '조', True, 'all', '발췌 포함(법률·시행령·시행규칙) · 조 단위'),
    ('with_excerpt', '항', True, 'all', '발췌 포함 · 항 단위'),
]
summary = []
for ver, unit, norm, conf, title in configs:
    S = year_sets(ver, unit, norm, conf)
    p(f'## {title}')
    p()
    p('### 주 결과 (Y = 2022~2026, 10년 창이 꽉 참)')
    p()
    tot, extra = backtest(S, MAIN)
    p('10년 풀로만 추가로 맞힌 조문 (Y, 조문, 직전 출제 후 경과 연수):')
    for y, lab, gap in extra:
        p(f'- {y}: {lab} ({gap}년 전)')
    p()
    p('### 참고 (Y = 2017~2021, 10년 창이 2012에서 잘림)')
    p()
    tref, extra_ref = backtest(S, REF)
    p('참고 구간 10년 풀 추가 적중:')
    for y, lab, gap in extra_ref:
        p(f'- {y}: {lab} ({gap}년 전)')
    p()
    summary.append((title, tot, tref))

    # N-curve over MAIN
    p('### 창 길이 N별 (Y = 2022~2026 합산)')
    p()
    p('| N | 적중/출제 | recall | 평균 풀 크기 | N-1 대비 추가 적중 | N-1 대비 풀 증가 |')
    p('|---|---|---|---|---|---|')
    prev = None
    nA = sum(len(S[y]) for y in MAIN)
    for n in range(1, 15):
        if n > 10:
            hits = sum(len(S[y] & pool(S, y, n)) for y in MAIN)
            ps = sum(len(pool(S, y, n)) for y in MAIN) / len(MAIN)
            note = ' (2012 이전 자료 없음: 일부 해만 늘어남)'
        else:
            hits = sum(len(S[y] & pool(S, y, n)) for y in MAIN)
            ps = sum(len(pool(S, y, n)) for y in MAIN) / len(MAIN)
            note = ''
        if prev:
            p(f'| {n}{note} | {hits}/{nA} | {pct(hits / nA)} | {ps:.1f} | +{hits - prev[0]} | +{ps - prev[1]:.1f} |')
        else:
            p(f'| {n} | {hits}/{nA} | {pct(hits / nA)} | {ps:.1f} | | |')
        prev = (hits, ps)
    p()

    if ver == 'core' and conf == 'all' and norm:
        occ, g = gaps(S)
        multi = {k: v for k, v in occ.items() if len(v) >= 2}
        p(f'### 재출제 간격 ({unit} 단위)')
        p()
        p(f'- 15년 동안 한 번이라도 나온 조문 {len(occ)}개, 두 해 이상 나온 조문 {len(multi)}개, 한 해만 나온 조문 {len(occ) - len(multi)}개')
        b = collections.Counter('1~5년' if d <= 5 else ('6~10년' if d <= 10 else '11년+') for d, *_ in g)
        n = len(g)
        p(f'- 연속 출제 간격 {n}건: 1~5년 {b["1~5년"]} ({pct(b["1~5년"] / n)}), 6~10년 {b["6~10년"]} ({pct(b["6~10년"] / n)}), 11년+ {b["11년+"]} ({pct(b["11년+"] / n)})')
        hist = collections.Counter(d for d, *_ in g)
        p('- 간격별 건수: ' + ', '.join(f'{d}년 {hist[d]}' for d in sorted(hist)))
        p('- 6년 이상 간격 목록: ' + '; '.join(f'{label(k)} {a}→{b2}' for d, k, a, b2 in sorted(g, key=lambda x: (-x[0], x[1])) if d >= 6))
        # observable-window view
        sl = since_last(S, MAIN)
        bc2 = collections.Counter('1~5년' if d <= 5 else ('6~10년' if d <= 10 else '11년+') for d, *_ in sl)
        p(f'- Y=2022~2026에 다시 나온 조문의 "직전 출제 후 경과 연수" {len(sl)}건: 1~5년 {bc2["1~5년"]}, 6~10년 {bc2["6~10년"]}, 11년+ {bc2["11년+"]}')
        p()
        p(f'### 출제 빈도 상위 ({unit} 단위, 출제 연도 수)')
        p()
        top = sorted(occ.items(), key=lambda kv: (-len(kv[1]), label(kv[0])))
        for k, ys in top:
            if len(ys) < 3:
                break
            p(f'- {label(k)}: {len(ys)}회 ({", ".join(str(y) for y in sorted(ys))})')
        p()

p('## 설정별 요약 (Y=2022~2026 합산)')
p()
p('| 설정 | 출제 | recall5 | recall10 | 추가 적중 | 평균 풀5 | 평균 풀10 |')
p('|---|---|---|---|---|---|---|')
for title, t, tr in summary:
    n = t['A']
    p(f"| {title} | {n} | {pct(t['h5'] / n)} | {pct(t['h10'] / n)} | {t['extra']} | {t['p5'] / 5:.1f} | {t['p10'] / 5:.1f} |")
p()
p('## 설정별 요약 (참고 Y=2017~2021 합산, 10년 창 잘림)')
p()
p('| 설정 | 출제 | recall5 | recall10 | 추가 적중 | 평균 풀5 | 평균 풀10 |')
p('|---|---|---|---|---|---|---|')
for title, t, tr in summary:
    n = tr['A']
    p(f"| {title} | {n} | {pct(tr['h5'] / n)} | {pct(tr['h10'] / n)} | {tr['extra']} | {tr['p5'] / 5:.1f} | {tr['p10'] / 5:.1f} |")
OUT.close()
