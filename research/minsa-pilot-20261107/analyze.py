"""Backtest 5-year vs 10-year retention windows on the 민사법 mapping, and set
it side by side with the 공법 pilot computed by the same code.

Copied from pilot-gongbeop/scripts/analyze.py + extra.py and extended.

Usage: python3 -I analyze.py MINSA.jsonl MINSA_meta.json GONGBEOP.jsonl OUT.md
"""
import collections
import json
import math
import random
import sys

MROWS = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
META = json.load(open(sys.argv[2], encoding='utf-8'))
GROWS = [json.loads(l) for l in open(sys.argv[3], encoding='utf-8')]
OUT = open(sys.argv[4], 'w', encoding='utf-8')
YEARS = list(range(2012, 2027))
MAIN = list(range(2022, 2027))
REF = list(range(2017, 2022))
SUBQ = {int(y): [tuple(x) for x in v] for y, v in META['subq'].items()}
SHANG = {int(y): v for y, v in META['shang'].items()}
BROW = {i: name for i, name in META['bundle_rows']}
for i, r in enumerate(MROWS):
    r['_bundle'] = BROW.get(i)


def p(*a):
    print(*a, file=OUT)


def pct(x):
    return f'{100 * x:.0f}%'


def key(r, unit='조', normalize=True):
    law, art, para = r['law'], r['article'], r['para']
    if normalize and 'current' in r:
        law = r['current'].get('law', law)
        art, para = r['current']['article'], r['current']['para']
    if unit == '조':
        return (law, art)
    return (law, art, para)


def label(k):
    s = f'{k[0]} {k[1]}조'
    if len(k) == 3 and k[2]:
        s += f' {k[2]}항'
    return s


def use(r, version, conf, nobundle=False):
    if version == 'core' and r['basis'] == '문제지 발췌':
        return False
    if version == 'with_excerpt' and r['kind'] in ('자치법규', '행정규칙'):
        return False
    if conf == 'sure' and r['confidence'] != '확실':
        return False
    if nobundle and r.get('_bundle'):
        return False
    return True


def year_sets(rows, version='core', unit='조', normalize=True, conf='all', nobundle=False):
    sets = {y: set() for y in YEARS}
    for r in rows:
        if use(r, version, conf, nobundle):
            sets[r['year']].add(key(r, unit, normalize))
    return sets


def subq_sets(rows, version='core', unit='조', conf='all'):
    sq = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        if use(r, version, conf):
            sq[r['year']][(r['q'], r['sub'])].add(key(r, unit))
    return sq


def pool(sets, y, n):
    out = set()
    for t in range(max(2012, y - n), y):
        out |= sets[t]
    return out


def wilson(k, n, z=1.96):
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def totals(sets, years):
    t = collections.Counter()
    for y in years:
        A = sets[y]
        p5, p10, pall = pool(sets, y, 5), pool(sets, y, 10), pool(sets, y, 99)
        t.update(A=len(A), h5=len(A & p5), h10=len(A & p10), hall=len(A & pall),
                 p5=len(p5), p10=len(p10), extra=len((A & p10) - p5))
    return t


def backtest(sets, years):
    tot = collections.Counter()
    extra_list = []
    p('| 목표 연도 Y | 출제 조문 수 A_Y | 5년 풀 적중 (recall5) | 10년 풀 적중 (recall10) | 전체 이력 적중 | 5년 풀 크기 | 10년 풀 크기 | 10년 창 | 10년 풀로만 추가 적중 |')
    p('|---|---|---|---|---|---|---|---|---|')
    for y in years:
        A = sets[y]
        p5, p10, pall = pool(sets, y, 5), pool(sets, y, 10), pool(sets, y, 99)
        h5, h10, hall = A & p5, A & p10, A & pall
        extra = h10 - h5
        p(f'| {y} | {len(A)} | {len(h5)} ({pct(len(h5) / len(A))}) | {len(h10)} ({pct(len(h10) / len(A))}) | {len(hall)} ({pct(len(hall) / len(A))}) | {len(p5)} | {len(p10)} | {max(2012, y - 10)}–{y - 1} | {len(extra)} |')
        tot.update(A=len(A), h5=len(h5), h10=len(h10), hall=len(hall), p5=len(p5), p10=len(p10), extra=len(extra))
        for k in sorted(extra):
            last = max(t for t in range(2012, y) if k in sets[t])
            extra_list.append((y, k, y - last))
    n = tot['A']
    l5, u5 = wilson(tot['h5'], n)
    l10, u10 = wilson(tot['h10'], n)
    ny = len(years)
    p(f"| **합계** | {n} | {tot['h5']} ({pct(tot['h5'] / n)}) | {tot['h10']} ({pct(tot['h10'] / n)}) | {tot['hall']} ({pct(tot['hall'] / n)}) | 평균 {tot['p5'] / ny:.1f} | 평균 {tot['p10'] / ny:.1f} | | {tot['extra']} |")
    p()
    p(f"- 합산 recall5 = {tot['h5']}/{n} = {pct(tot['h5'] / n)} (95% Wilson {pct(l5)}–{pct(u5)}), recall10 = {tot['h10']}/{n} = {pct(tot['h10'] / n)} (95% {pct(l10)}–{pct(u10)}), 전체 이력 상한 {pct(tot['hall'] / n)}")
    dp = (tot['p10'] - tot['p5']) / ny
    p(f"- 10년 창이 더 덮은 몫: {tot['extra']}/{n} = {pct(tot['extra'] / n)}p. 대신 풀은 해마다 평균 {dp:.1f}개(+{100 * dp / (tot['p5'] / ny):.0f}%) 늘어남.")
    p(f"- 풀 1개당 적중(5년 합산): 5년 풀 {tot['h5'] / tot['p5']:.3f}, 6~10년 구간에만 있는 조문 {tot['extra'] / max(1, tot['p10'] - tot['p5']):.3f}")
    p()
    return tot, extra_list


def ncurve(sets, years):
    nA = sum(len(sets[y]) for y in years)
    out = []
    for n in range(1, 15):
        hits = sum(len(sets[y] & pool(sets, y, n)) for y in years)
        ps = sum(len(pool(sets, y, n)) for y in years) / len(years)
        out.append((n, hits, nA, ps))
    return out


def print_ncurve(curve):
    p('| N | 적중/출제 | recall | 평균 풀 크기 | N-1 대비 추가 적중 | N-1 대비 풀 증가 | 그 구간 추가 조문 1개당 적중(5년 합산) |')
    p('|---|---|---|---|---|---|---|')
    prev = None
    for n, hits, nA, ps in curve:
        note = ' (2012 이전 자료 없음)' if n > 10 else ''
        if prev:
            dh, dps = hits - prev[0], ps - prev[1]
            eff = f'{dh / (dps * 5):.3f}' if dps > 0 else '–'
            p(f'| {n}{note} | {hits}/{nA} | {pct(hits / nA)} | {ps:.1f} | +{dh} | +{dps:.1f} | {eff} |')
        else:
            p(f'| {n} | {hits}/{nA} | {pct(hits / nA)} | {ps:.1f} | | | {hits / (ps * 5):.3f} |')
        prev = (hits, ps)
    p()


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
    out = []
    for y in years:
        for k in sets[y]:
            prev = [t for t in range(2012, y) if k in sets[t]]
            if prev:
                out.append((y - max(prev), y, k))
    return out


def bucket(d):
    return '1~5년' if d <= 5 else ('6~10년' if d <= 10 else '11년+')


def gap_report(sets, unit):
    occ, g = gaps(sets)
    multi = {k: v for k, v in occ.items() if len(v) >= 2}
    p(f'- 15년 동안 한 번이라도 나온 조문 {len(occ)}개, 두 해 이상 나온 조문 {len(multi)}개, 한 해만 나온 조문 {len(occ) - len(multi)}개')
    b = collections.Counter(bucket(d) for d, *_ in g)
    n = len(g)
    p(f'- 연속 출제 간격 {n}건: 1~5년 {b["1~5년"]} ({pct(b["1~5년"] / n)}), 6~10년 {b["6~10년"]} ({pct(b["6~10년"] / n)}), 11년+ {b["11년+"]} ({pct(b["11년+"] / n)})')
    hist = collections.Counter(d for d, *_ in g)
    p('- 간격별 건수: ' + ', '.join(f'{d}년 {hist[d]}' for d in sorted(hist)))
    p('- 6년 이상 간격 목록: ' + '; '.join(f'{label(k)} {a}→{b2}' for d, k, a, b2 in sorted(g, key=lambda x: (-x[0], x[1])) if d >= 6))
    sl = since_last(sets, MAIN)
    bc2 = collections.Counter(bucket(d) for d, *_ in sl)
    h2 = collections.Counter(d for d, *_ in sl)
    p(f'- Y=2022~2026에 다시 나온 조문의 직전 출제 후 경과 연수 {len(sl)}건: 1~5년 {bc2["1~5년"]}, 6~10년 {bc2["6~10년"]}, 11년+ {bc2["11년+"]} (연수별: ' + ', '.join(f'{d}년 {h2[d]}' for d in sorted(h2)) + ')')
    p()
    return occ, g


def bootstrap(rows, unit='조', conf='all', B=5000, seed=1):
    S = year_sets(rows, 'core', unit, True, conf)
    SQ = subq_sets(rows, 'core', unit, conf)
    random.seed(seed)
    r5s, r10s, d = [], [], []
    for _ in range(B):
        hA = h5 = h10 = 0
        for y in MAIN:
            subs = list(SQ[y].values())
            samp = [random.choice(subs) for _ in subs]
            A = set().union(*samp)
            p5, p10 = pool(S, y, 5), pool(S, y, 10)
            hA += len(A)
            h5 += len(A & p5)
            h10 += len(A & p10)
        r5s.append(h5 / hA)
        r10s.append(h10 / hA)
        d.append((h10 - h5) / hA)
    res = {}
    for name, v in (('recall5', r5s), ('recall10', r10s), ('추가 적중 몫', d)):
        v.sort()
        res[name] = (v[B // 2], v[int(B * .025)], v[int(B * .975)])
    return res


def civil_book(art):
    try:
        n = int(art.split('의')[0])
    except ValueError:
        return '기타'
    if n <= 184:
        return '총칙'
    if n <= 372:
        return '물권'
    if n <= 526:
        return '채권총론'
    if n <= 766:
        return '채권각론'
    if n <= 996:
        return '친족'
    return '상속'


def group(k, fine=False):
    law = k[0]
    if law == '민법':
        return '민법·' + civil_book(k[1]) if fine else '민법'
    if law in ('민사소송법', '민사집행법'):
        return law
    return '기타(특별법·상법)'


def law_breakdown(sets, fine):
    cnt = collections.defaultdict(collections.Counter)
    for y in MAIN:
        p5, p10, pall = pool(sets, y, 5), pool(sets, y, 10), pool(sets, y, 99)
        for a in sets[y]:
            cat = 'hit5' if a in p5 else ('extra10' if a in p10 else ('older' if a in pall else 'new'))
            cnt[group(a, fine)][cat] += 1
    comp5 = collections.Counter()
    comp10 = collections.Counter()
    for y in MAIN:
        for a in pool(sets, y, 5):
            comp5[group(a, fine)] += 1
        for a in pool(sets, y, 10):
            comp10[group(a, fine)] += 1
    p('| 구분 | 출제(5년 합산) | 5년 풀 적중 | 10년으로만 추가 적중 | 11년+ 전에만 | 처음 나옴 | recall5 | recall10 | 평균 풀5 | 평균 풀10 | 늘어난 풀 1개당 추가 적중 |')
    p('|---|---|---|---|---|---|---|---|---|---|---|')
    for g in sorted(cnt, key=lambda g: -sum(cnt[g].values())):
        c = cnt[g]
        n = sum(c.values())
        add = (comp10[g] - comp5[g])
        eff = f'{c["extra10"] / add:.3f}' if add else '–'
        p(f'| {g} | {n} | {c["hit5"]} | {c["extra10"]} | {c["older"]} | {c["new"]} | {pct(c["hit5"] / n)} | {pct((c["hit5"] + c["extra10"]) / n)} | {comp5[g] / 5:.1f} | {comp10[g] / 5:.1f} | {eff} |')
    p()
    return cnt


def headline(rows, unit='조', conf='all', version='core'):
    S = year_sets(rows, version, unit, True, conf)
    t = totals(S, MAIN)
    return S, t


# ================================================================== report
p('# 민사법 사례형 시범 분석 출력 (자동 생성)')
p()
p(f'mapping 줄 수: {len(MROWS)}')
bc = collections.Counter((r['basis'], r['confidence']) for r in MROWS)
p('basis·confidence: ' + ', '.join(f'{a}/{b} {c}' for (a, b), c in sorted(bc.items())))
core_rows = [r for r in MROWS if r['basis'] != '문제지 발췌']
p(f'발췌 제외 줄 {len(core_rows)}: 확실 {sum(r["confidence"] == "확실" for r in core_rows)}, 확인 필요 {sum(r["confidence"] != "확실" for r in core_rows)}; 쟁점 묶음(bundle)으로 들어간 줄 {sum(1 for r in core_rows if r["_bundle"])}')
lawc = collections.Counter(r['law'] for r in core_rows)
p('법령별 줄 수(발췌 제외): ' + ', '.join(f'{a} {c}' for a, c in lawc.most_common()))
p()
nsub = sum(len(v) for v in SUBQ.values())
anch = collections.defaultdict(set)
for r in core_rows:
    anch[(r['year'], r['q'], r['sub'])].add(group(key(r)))
none = [(y, q, s) for y, v in SUBQ.items() for q, s in v if (y, q, s) not in anch]
p(f'민사 설문 수 {nsub} (상법 설문 {sum(SHANG.values())}개는 수만 셈). 발췌 외 조문이 1개 이상 매핑된 설문 {nsub - len(none)}, 근거 조문 없음 {len(none)}')
p('근거 조문 없는 설문: ' + ', '.join(f'{y} {q}-{s}' for y, q, s in none))
lawsub = collections.Counter()
for k, gs in anch.items():
    for g in gs:
        lawsub[g] += 1
p('법령이 걸린 설문 수(중복 셈): ' + ', '.join(f'{g} {c}' for g, c in lawsub.most_common()))
p()
p('| 연도 | 민사 설문 | 민법 걸림 | 민소 걸림 | 민집 걸림 | 기타 걸림 | 근거 조문 없음 | 상법 설문 |')
p('|---|---|---|---|---|---|---|---|')
for y in YEARS:
    ks = [(y, q, s) for q, s in SUBQ[y]]
    c = collections.Counter(g for k in ks for g in anch.get(k, ()))
    p(f'| {y} | {len(ks)} | {c["민법"]} | {c["민사소송법"]} | {c["민사집행법"]} | {c["기타(특별법·상법)"]} | {sum(1 for k in ks if k not in anch)} | {SHANG[y]} |')
p()

configs = [
    ('core', '조', True, 'all', False, '발췌 제외 · 조 단위 · 현행 번호 정규화 · 전체 신뢰도 (주 결과)'),
    ('core', '항', True, 'all', False, '발췌 제외 · 항 단위'),
    ('core', '조', False, 'all', False, '발췌 제외 · 조 단위 · 출제 당시 번호(정규화 안 함)'),
    ('core', '조', True, 'sure', False, '발췌 제외 · 조 단위 · 확실만'),
    ('core', '조', True, 'all', True, '발췌 제외 · 조 단위 · 쟁점 묶음으로만 들어간 출현 제외(묶음 효과 하한)'),
    ('with_excerpt', '조', True, 'all', False, '발췌 포함 · 조 단위'),
]
summary = []
for ver, unit, norm, conf, nob, title in configs:
    S = year_sets(MROWS, ver, unit, norm, conf, nob)
    p(f'## {title}')
    p()
    p('### 주 결과 (Y = 2022~2026, 10년 창이 꽉 참)')
    p()
    tot, extra = backtest(S, MAIN)
    p('10년 풀로만 추가로 맞힌 조문 (Y, 조문, 직전 출제 후 경과 연수):')
    for y, k, gap in extra:
        p(f'- {y}: {label(k)} ({gap}년 전)')
    p()
    p('### 참고 (Y = 2017~2021, 10년 창이 2012에서 잘림)')
    p()
    tref, extra_ref = backtest(S, REF)
    p('참고 구간 10년 풀 추가 적중: ' + '; '.join(f'{y} {label(k)}({g}년 전)' for y, k, g in extra_ref))
    p()
    summary.append((title, tot, tref))
    p('### 창 길이 N별 (Y = 2022~2026 합산)')
    p()
    print_ncurve(ncurve(S, MAIN))
    if ver == 'core' and conf == 'all' and norm and not nob:
        p(f'### 재출제 간격 ({unit} 단위)')
        p()
        occ, g = gap_report(S, unit)
        p(f'### 출제 빈도 상위 ({unit} 단위, 출제 연도 수 4 이상)')
        p()
        top = sorted(occ.items(), key=lambda kv: (-len(kv[1]), label(kv[0])))
        for k, ys in top:
            if len(ys) < 4:
                break
            p(f'- {label(k)}: {len(ys)}회 ({", ".join(str(y) for y in sorted(ys))})')
        p()

p('## 설정별 요약 (Y=2022~2026 합산)')
p()
p('| 설정 | 출제 | recall5 | recall10 | 차이 | 추가 적중 | 평균 풀5 | 평균 풀10 | 풀 증가율 |')
p('|---|---|---|---|---|---|---|---|---|')
for title, t, tr in summary:
    n = t['A']
    p(f"| {title} | {n} | {pct(t['h5'] / n)} | {pct(t['h10'] / n)} | +{100 * (t['h10'] - t['h5']) / n:.0f}%p | {t['extra']} | {t['p5'] / 5:.1f} | {t['p10'] / 5:.1f} | +{100 * (t['p10'] - t['p5']) / t['p5']:.0f}% |")
p()
p('## 설정별 요약 (참고 Y=2017~2021 합산, 10년 창 잘림)')
p()
p('| 설정 | 출제 | recall5 | recall10 | 추가 적중 | 평균 풀5 | 평균 풀10 |')
p('|---|---|---|---|---|---|---|')
for title, t, tr in summary:
    n = tr['A']
    p(f"| {title} | {n} | {pct(tr['h5'] / n)} | {pct(tr['h10'] / n)} | {tr['extra']} | {tr['p5'] / 5:.1f} | {tr['p10'] / 5:.1f} |")
p()

# ---------------------------------------------------------------- bootstrap
p('## 설문 군집 부트스트랩 (Y=2022~2026, 풀 고정, B=5000)')
p()
p('| 자료 · 설정 | recall5 중앙 (95%) | recall10 중앙 (95%) | 추가 적중 몫 중앙 (95%) |')
p('|---|---|---|---|')
BOOT = {}
for nm, rows in (('민사', MROWS), ('공법', GROWS)):
    for unit, conf, t in (('조', 'all', '조 · 전체'), ('조', 'sure', '조 · 확실만'), ('항', 'all', '항 · 전체')):
        res = bootstrap(rows, unit, conf)
        BOOT[(nm, unit, conf)] = res
        cell = lambda v: f'{pct(v[0])} ({pct(v[1])}–{pct(v[2])})'
        p(f'| {nm} · {t} | {cell(res["recall5"])} | {cell(res["recall10"])} | {cell(res["추가 적중 몫"])} |')
p()

# ---------------------------------------------------------------- law breakdown
S = year_sets(MROWS)
p('## 법령별 분해 (Y=2022~2026, 조 단위, 주 설정)')
p()
law_breakdown(S, fine=False)
p('### 민법 편별')
p()
law_breakdown(S, fine=True)
p('### 10년 풀로만 추가 적중한 조문의 법령·편')
p()
_, extra = backtest_quiet = (None, None)
ex = []
for y in MAIN:
    p5, p10 = pool(S, y, 5), pool(S, y, 10)
    for k in sorted((S[y] & p10) - p5):
        ex.append((y, k, group(k, True)))
cc = collections.Counter(g for *_, g in ex)
p(', '.join(f'{g} {c}' for g, c in cc.most_common()))
p()

# ---------------------------------------------------------------- bundle effect
p('## 쟁점 묶음(bundle) 효과')
p()
bund_art = collections.defaultdict(set)
for r in core_rows:
    bund_art[(r['year'], key(r))].add('B' if r['_bundle'] else 'I')
hits5 = [(y, k) for y in MAIN for k in S[y] & pool(S, y, 5)]
hitsx = [(y, k) for y in MAIN for k in (S[y] & pool(S, y, 10)) - pool(S, y, 5)]
for nm, hs in (('5년 풀 적중', hits5), ('10년으로만 추가 적중', hitsx)):
    onlyb = sum(1 for y, k in hs if bund_art[(y, k)] == {'B'})
    p(f'- {nm} {len(hs)}건 중 목표 연도 출현이 묶음 줄로만 이루어진 것 {onlyb}건')
bnames = collections.Counter(r['_bundle'] for r in core_rows if r['_bundle'])
p('- 묶음 사용 횟수 상위: ' + ', '.join(f'{a} {c}' for a, c in bnames.most_common(15)))
p()

# ---------------------------------------------------------------- hybrid rules
p('## 혼합 규칙 (Y=2022~2026, 조 단위)')
p()
p('| 규칙 | recall | 평균 풀 |')
p('|---|---|---|')


def hybrid(sets, keep_all, n_other=5, n_keep=99):
    hA = h = ps = 0
    for y in MAIN:
        P = set(a for a in pool(sets, y, n_keep) if keep_all(a)) | set(a for a in pool(sets, y, n_other) if not keep_all(a))
        hA += len(sets[y])
        h += len(sets[y] & P)
        ps += len(P)
    return h, hA, ps / 5


rules = [
    ('전체 5년', lambda a: False, 5, 99),
    ('전체 10년', lambda a: False, 10, 99),
    ('민사소송법만 10년 + 나머지 5년', lambda a: a[0] == '민사소송법', 5, 10),
    ('민법만 10년 + 나머지 5년', lambda a: a[0] == '민법', 5, 10),
    ('민법 총칙·채권총론만 10년 + 나머지 5년', lambda a: a[0] == '민법' and civil_book(a[1]) in ('총칙', '채권총론'), 5, 10),
    ('5년 안에 2회 이상 나온 조문만(5년)', None, None, None),
    ('10년 안에 2회 이상 나온 조문 + 5년 안 1회 이상', None, None, None),
]
for nm, f, n_other, n_keep in rules:
    if f is not None:
        h, hA, ps = hybrid(S, f, n_other, n_keep)
    elif nm.startswith('5년 안에 2회'):
        hA = h = ps = 0
        for y in MAIN:
            P = set(a for a in pool(S, y, 5) if sum(a in S[t] for t in range(y - 5, y)) >= 2)
            hA += len(S[y]); h += len(S[y] & P); ps += len(P)
        ps /= 5
    else:
        hA = h = ps = 0
        for y in MAIN:
            P = pool(S, y, 5) | set(a for a in pool(S, y, 10) if sum(a in S[t] for t in range(y - 10, y)) >= 2)
            hA += len(S[y]); h += len(S[y] & P); ps += len(P)
        ps /= 5
    p(f'| {nm} | {h}/{hA} = {pct(h / hA)} | {ps:.1f} |')
p()

# ---------------------------------------------------------------- side by side with 공법
p('## 공법 시범과 나란히 (같은 코드로 다시 계산)')
p()
rowsets = {'공법': GROWS, '민사': MROWS}
p('| 지표 | 공법 | 민사 |')
p('|---|---|---|')
vals = collections.defaultdict(dict)
for nm, rows in rowsets.items():
    S2, t = headline(rows)
    n = t['A']
    vals['출제 조문 수(5년 합산)'][nm] = f"{n}"
    vals['recall5'][nm] = f"{t['h5']}/{n} = {pct(t['h5'] / n)}"
    vals['recall10'][nm] = f"{t['h10']}/{n} = {pct(t['h10'] / n)}"
    vals['차이(%p)'][nm] = f"+{100 * (t['h10'] - t['h5']) / n:.0f}"
    b = BOOT[(nm, '조', 'all')]['추가 적중 몫']
    vals['차이 95% (설문 군집 부트스트랩)'][nm] = f'{pct(b[1])}–{pct(b[2])}'
    vals['전체 이력 상한'][nm] = pct(t['hall'] / n)
    vals['처음 나온 조문 몫'][nm] = pct(1 - t['hall'] / n)
    vals['평균 풀5 → 풀10'][nm] = f"{t['p5'] / 5:.1f} → {t['p10'] / 5:.1f} (+{100 * (t['p10'] - t['p5']) / t['p5']:.0f}%)"
    vals['풀5 1개당 적중'][nm] = f"{t['h5'] / t['p5']:.3f}"
    vals['6~10년 구간 조문 1개당 적중'][nm] = f"{t['extra'] / (t['p10'] - t['p5']):.3f}"
    for unit, conf, lab in (('항', 'all', '항 단위'), ('조', 'sure', '확실만')):
        _, t2 = headline(rows, unit, conf)
        n2 = t2['A']
        vals[f'{lab} recall5 → recall10'][nm] = f"{pct(t2['h5'] / n2)} → {pct(t2['h10'] / n2)} (+{100 * (t2['h10'] - t2['h5']) / n2:.0f}%p)"
    _, tr = None, totals(S2, REF)
    vals['참고 2017~2021 recall5 → recall10'][nm] = f"{pct(tr['h5'] / tr['A'])} → {pct(tr['h10'] / tr['A'])}"
    occ, g = gaps(S2)
    bb = collections.Counter(bucket(d) for d, *_ in g)
    vals['연속 간격 1~5 / 6~10 / 11+'][nm] = f"{bb['1~5년']} / {bb['6~10년']} / {bb['11년+']} ({pct(bb['1~5년'] / len(g))} / {pct(bb['6~10년'] / len(g))} / {pct(bb['11년+'] / len(g))})"
    multi = sum(1 for v in occ.values() if len(v) >= 2)
    vals['15년 서로 다른 조문 / 2해 이상'][nm] = f'{len(occ)} / {multi} ({pct(multi / len(occ))})'
    cur = ncurve(S2, MAIN)
    vals['N=3/5/7/10 recall'][nm] = ' / '.join(pct(h / nA) for n, h, nA, ps in cur if n in (3, 5, 7, 10))
    vals['N=3/5/7/10 평균 풀'][nm] = ' / '.join(f'{ps:.0f}' for n, h, nA, ps in cur if n in (3, 5, 7, 10))
    # per-year extra
    per = []
    for y in MAIN:
        p5, p10 = pool(S2, y, 5), pool(S2, y, 10)
        per.append(f"{len((S2[y] & p10) - p5)}/{len(S2[y])}")
    vals['연도별 추가 적중/출제 (2022→2026)'][nm] = ', '.join(per)
for k, v in vals.items():
    p(f"| {k} | {v.get('공법', '')} | {v.get('민사', '')} |")
p()

# ---------------------------------------------------------------- 효율 부트스트랩과 공법-민사 차이
p('## 효율 부트스트랩 (Y=2022~2026, 설문 군집, 풀 고정, B=5000)')
p()


def eff_boot(rows, B=5000, seed=7):
    S = year_sets(rows)
    SQ = subq_sets(rows)
    P5 = {y: pool(S, y, 5) for y in MAIN}
    P10 = {y: pool(S, y, 10) for y in MAIN}
    add = sum(len(P10[y]) - len(P5[y]) for y in MAIN)
    base = sum(len(P5[y]) for y in MAIN)
    random.seed(seed)
    out = []
    for _ in range(B):
        h5 = hx = hA = 0
        for y in MAIN:
            subs = list(SQ[y].values())
            A = set().union(*[random.choice(subs) for _ in subs])
            hA += len(A)
            h5 += len(A & P5[y])
            hx += len((A & P10[y]) - P5[y])
        e5, ex = h5 / base, hx / add
        out.append((hx / hA, e5, ex, ex / e5 if e5 else float('nan')))
    return out


EB = {nm: eff_boot(rows) for nm, rows in (('공법', GROWS), ('민사', MROWS))}


def q(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2], v[int(n * .025)], v[int(n * .975)]


p('재표집에서는 같은 설문이 겹쳐 뽑혀 고유 조문 수가 줄므로 1개당 적중의 절대값은 점추정보다 낮게 나온다. 비교는 비율로 한다.')
p()
p('| 자료 | 풀5 1개당 적중(재표집 중앙) | 6~10년 조문 1개당 적중(재표집 중앙) | 비율(6~10년 ÷ 풀5) | 비율<1일 확률 |')
p('|---|---|---|---|---|')
for nm, v in EB.items():
    a, b_, c = q([x[1] for x in v]), q([x[2] for x in v]), q([x[3] for x in v])
    lt1 = sum(1 for x in v if x[3] < 1) / len(v)
    p(f'| {nm} | {a[0]:.3f} ({a[1]:.3f}–{a[2]:.3f}) | {b_[0]:.3f} ({b_[1]:.3f}–{b_[2]:.3f}) | {c[0]:.2f} ({c[1]:.2f}–{c[2]:.2f}) | {pct(lt1)} |')
p()
dd = [g[0] - m[0] for g, m in zip(EB['공법'], EB['민사'])]
de = [g[3] - m[3] for g, m in zip(EB['공법'], EB['민사'])]
a, b_ = q(dd), q(de)
p(f'- 추가 적중 몫 차이(공법 − 민사, 두 자료를 독립 재표집): 중앙 {100 * a[0]:.0f}%p, 95% {100 * a[1]:.0f}–{100 * a[2]:.0f}%p, 차이≤0일 확률 {pct(sum(1 for x in dd if x <= 0) / len(dd))}')
p(f'- 효율 비율 차이(공법 − 민사): 중앙 {b_[0]:.2f}, 95% {b_[1]:.2f}–{b_[2]:.2f}, 차이≤0일 확률 {pct(sum(1 for x in de if x <= 0) / len(de))}')
p()

# ---------------------------------------------------------------- 참고 구간 법령 분해와 혼합 규칙(사후 선택 점검)
p('## 참고 구간(Y=2017~2021) 법령별 추가 적중 (10년 창 잘림)')
p()
cntr = collections.Counter()
for y in REF:
    p5, p10 = pool(S, y, 5), pool(S, y, 10)
    for k in (S[y] & p10) - p5:
        cntr[group(k, True)] += 1
p(', '.join(f'{g} {c}' for g, c in cntr.most_common()) or '없음')
p()
p('| 규칙 (참고 구간) | recall | 평균 풀 |')
p('|---|---|---|')


def hybrid_years(sets, keep, years, n_other=5, n_keep=10):
    hA = h = ps = 0
    for y in years:
        P = set(a for a in pool(sets, y, n_keep) if keep(a)) | set(a for a in pool(sets, y, n_other) if not keep(a))
        hA += len(sets[y]); h += len(sets[y] & P); ps += len(P)
    return h, hA, ps / len(years)


for nm, f in (('전체 5년', lambda a: False), ('민사소송법만 10년 + 나머지 5년', lambda a: a[0] == '민사소송법'),
              ('민법만 10년 + 나머지 5년', lambda a: a[0] == '민법'), ('전체 10년', lambda a: True)):
    h, hA, ps = hybrid_years(S, f, REF)
    p(f'| {nm} | {h}/{hA} = {pct(h / hA)} | {ps:.1f} |')
p()

# ---------------------------------------------------------------- 추가 적중의 설문 집중도
p('## 10년으로만 추가 적중한 조문이 몇 개 설문에서 나왔나 (Y=2022~2026)')
p()
SQm = subq_sets(MROWS)
src = collections.Counter()
for y in MAIN:
    p5, p10 = pool(S, y, 5), pool(S, y, 10)
    for k in (S[y] & p10) - p5:
        owners = [sk for sk, arts in SQm[y].items() if k in arts]
        for sk in owners:
            src[(y, sk)] += 1
p(f'- 추가 적중 25건이 걸친 설문 {len(src)}개; 설문별 건수: ' + ', '.join(f'{y} {a}-{b2} {c}' for (y, (a, b2)), c in sorted(src.items(), key=lambda kv: -kv[1])))
p()
OUT.close()
