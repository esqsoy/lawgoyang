"""사시 2차(2002~2017) + 변시(2012~2026) 공법 사례형 합집합 이력으로 창 길이 N 정하기.

Usage: python3 -I analyze_sasi.py SASI_MAPPING SASI_SUBQ PILOT_MAPPING OUT.md

Main definition (주 결과): 발췌 제외, 조 단위, 현행 번호, 사시 '이론' 설문 제외,
출제 당시 조문 없던 법리 행(article == '') 제외. 2012~2017은 두 시험 합집합.
"""
import collections
import json
import math
import random
import sys

import numpy as np

SASI = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
SUBQ = [json.loads(l) for l in open(sys.argv[2], encoding='utf-8')]
PILOT = [json.loads(l) for l in open(sys.argv[3], encoding='utf-8')]
OUT = open(sys.argv[4], 'w', encoding='utf-8')

QTYPE = {(s['year'], s['part'], s['q'], s['sub']): s['qtype'] for s in SUBQ}
Y0, Y1 = 2002, 2026
YEARS = list(range(Y0, Y1 + 1))
CORE3 = {'헌법', '헌법재판소법', '행정소송법'}

# 변시 2012~2020 법리 문항을 행정기본법 조문에 대는 보조 행(민감도 분석 전용, 모두 확인 필요).
# 시범 매핑은 2021년 이후에만 행정기본법을 넣었으므로, 사시의 법리 행을 넣을 때 이것도 함께 넣어야 비교가 맞는다.
OVERLAY = [
    (2012, '2', '3(3)', '17', '', '부관(부담)'),
    (2016, '1', '4', '15', '', '형사법원 선결문제와 처분의 효력'),
    (2016, '2', '3가', '17', '', '법령 근거 없는 부담'),
    (2016, '2', '3나', '17', '', '사후부관'),
    (2016, '2', '3다', '19', '', '철회권 유보와 철회'),
    (2019, '2', '4', '14', '', '처분 시 적용 법령(법 적용 기준)'),
]
for y, q, sub, art, para, issue in OVERLAY:
    PILOT.append({'year': y, 'part': '공법', 'q': q, 'sub': sub, 'law': '행정기본법', 'article': '',
                  'para': '', 'basis': 'Claude 판단', 'confidence': '확인 필요', 'issue': issue,
                  'kind': '법률', 'overlay': True,
                  'current': {'law': '행정기본법', 'article': art, 'para': para, 'note': '보조 행'}})


def p(*a):
    print(*a, file=OUT)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pc(x, nd=1):
    return '–' if x != x else f'{100 * x:.{nd}f}%'


def key(r, unit):
    law, art, para = r['law'], r['article'], r['para']
    cur = r.get('current')
    if cur == '없음':
        law = law + '(현행 없음)'
    elif isinstance(cur, dict):
        law = cur.get('law', law)
        art, para = cur['article'], cur['para']
        if art == '확인 필요':
            art = '?' + r['article']
    if unit == '조':
        return (law, art)
    return (law, art, para)


def year_sets(unit='조', conf='all', theory=False, prelaw=False, excerpt=False, src='both'):
    sets = {y: set() for y in YEARS}
    for r in SASI + PILOT:
        is_sasi = r['part'].startswith('사시')
        if src == 'sasi' and not is_sasi:
            continue
        if src == 'bs' and is_sasi:
            continue
        if not excerpt and r['basis'] == '문제지 발췌':
            continue
        if conf == 'sure' and r['confidence'] != '확실':
            continue
        if r['article'] == '':
            if not prelaw:
                continue
        if r.get('overlay') and not prelaw:
            continue
        if is_sasi and not theory and r['sub'] != '전체':
            if QTYPE[(r['year'], r['part'], r['q'], r['sub'])] == '이론':
                continue
        sets[r['year']].add(key(r, unit))
    return sets


def exposures(sets, targets=None, group=None):
    """Return list of (key, Y, g, hit) for every article seen before Y."""
    ex = []
    last = {}
    for Y in YEARS:
        if Y > Y0 and (targets is None or Y in targets):
            for k, ly in last.items():
                if group is not None and not group(k):
                    continue
                ex.append((k, Y, Y - ly, k in sets[Y]))
        for k in sets[Y]:
            last[k] = Y
    return ex


def tally(ex):
    risk, hit = collections.Counter(), collections.Counter()
    for _, _, g, h in ex:
        risk[g] += 1
        hit[g] += h
    return risk, hit


BANDS2 = [(a, a + 1) for a in range(1, 25, 2)]
BANDS3 = [(a, min(a + 2, 24)) for a in range(1, 25, 3)]


def band_rates(risk, hit, bands):
    out = []
    for a, b in bands:
        r = sum(risk[g] for g in range(a, b + 1))
        h = sum(hit[g] for g in range(a, b + 1))
        out.append((a, b, h, r))
    return out


def base_rate(risk, hit, lo=1, hi=5):
    r = sum(risk[g] for g in range(lo, hi + 1))
    h = sum(hit[g] for g in range(lo, hi + 1))
    return h / r if r else float('nan')


def rule(rates, thr, mode='point'):
    """Last band (upper g) whose hazard (point / Wilson lower / Wilson upper) >= thr.
    Also the first band that falls below thr (contiguous reading)."""
    last, first_below = None, None
    for a, b, h, r in rates:
        if r == 0:
            continue
        v = h / r
        lo, hi = wilson(h, r)
        val = {'point': v, 'lower': lo, 'upper': hi}[mode]
        if val >= thr:
            last = b
        elif first_below is None:
            first_below = a
    contig = (first_below - 1) if first_below else None
    return last, contig


def hazard_section(title, sets, targets=None, group=None, show_1y=True, boot=True):
    ex = exposures(sets, targets, group)
    risk, hit = tally(ex)
    base = base_rate(risk, hit)
    thr = base / 2
    p(f'### {title}')
    p()
    rb = sum(risk[g] for g in range(1, 6))
    hb = sum(hit[g] for g in range(1, 6))
    lo, hi = wilson(hb, rb)
    p(f'- 1~5년 평균 위험률 {hb}/{rb} = {pc(base)} (95% {pc(lo)}–{pc(hi)}), 절반 기준선 {pc(thr)}')
    if show_1y:
        p()
        p('| g | 위험(조문·연) | 재출제 | h(g) | 95% Wilson |')
        p('|---|---|---|---|---|')
        for g in range(1, 25):
            if risk[g]:
                l, u = wilson(hit[g], risk[g])
                p(f'| {g} | {risk[g]} | {hit[g]} | {pc(hit[g] / risk[g])} | {pc(l)}–{pc(u)} |')
    p()
    p('| 묶음 g | 위험 | 재출제 | h | 95% Wilson | 기준선 대비 |')
    p('|---|---|---|---|---|---|')
    rates2 = band_rates(risk, hit, BANDS2)
    for a, b, h, r in rates2:
        if r == 0:
            p(f'| {a}~{b} | 0 | 0 | – | – | 표본 없음 |')
            continue
        l, u = wilson(h, r)
        v = h / r
        mark = '이상' if v >= thr else '미만'
        if l >= thr:
            mark += ' (하한도 이상)'
        elif u < thr:
            mark += ' (상한도 미만)'
        p(f'| {a}~{b} | {r} | {h} | {pc(v)} | {pc(l)}–{pc(u)} | {mark} |')
    p()
    res = {}
    for nm, bands in (('1년', [(g, g) for g in range(1, 25)]), ('2년', BANDS2), ('3년', BANDS3)):
        rates = band_rates(risk, hit, bands)
        rp, cp = rule(rates, thr, 'point')
        rl, cl = rule(rates, thr, 'lower')
        ru, cu = rule(rates, thr, 'upper')
        res[nm] = (rp, cp, rl, ru)
        p(f'- 잣대({nm} 묶음): 점추정 기준 마지막 g = **{rp}** (처음 기준선 밑으로 내려가기 직전 g = {cp}); '
          f'구간 하한 기준 {rl}, 구간 상한 기준 {ru}')
    if boot:
        bres = bootstrap_rule(ex)
        for nm, (dist, pr) in bres.items():
            items = ', '.join(f'{k}: {v / pr[1]:.0%}' for k, v in sorted(dist.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))
            p(f'- 조문 재표집 붓스트랩({pr[1]}회, {nm} 묶음) 잣대 N 분포: {items}; 95% 범위 {pr[0]}')
    p()
    return ex, risk, hit, base, res


def bootstrap_rule(ex, B=2000, seed=7):
    by = collections.defaultdict(list)
    for k, Y, g, h in ex:
        by[k].append((g, h))
    keys = list(by)
    rng = random.Random(seed)
    out = {}
    dists = {'2년': collections.Counter(), '3년': collections.Counter()}
    vals = {'2년': [], '3년': []}
    for _ in range(B):
        risk, hit = collections.Counter(), collections.Counter()
        for _k in range(len(keys)):
            k = keys[rng.randrange(len(keys))]
            for g, h in by[k]:
                risk[g] += 1
                hit[g] += h
        base = base_rate(risk, hit)
        for nm, bands in (('2년', BANDS2), ('3년', BANDS3)):
            n, _ = rule(band_rates(risk, hit, bands), base / 2)
            dists[nm][n] += 1
            vals[nm].append(n if n is not None else 0)
    for nm in dists:
        v = sorted(vals[nm])
        out[nm] = (dists[nm], (f'{v[int(0.025 * B)]}~{v[int(0.975 * B) - 1]}', B))
    return out


def logistic_fit(ex):
    g = np.array([e[2] for e in ex], dtype=float)
    y = np.array([1.0 if e[3] else 0.0 for e in ex])
    X = np.column_stack([np.ones_like(g), np.log(g)])
    b = np.zeros(2)
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ b))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None])
        grad = X.T @ (y - mu)
        step = np.linalg.solve(H, grad)
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def logistic_section(title, ex, B=1000, seed=11):
    def nstar(b, base):
        thr = base / 2
        lt = math.log(thr / (1 - thr))
        if b[1] >= 0:
            return float('inf')
        return math.exp((lt - b[0]) / b[1])

    risk, hit = tally(ex)
    base = base_rate(risk, hit)
    b = logistic_fit(ex)
    ns = nstar(b, base)
    by = collections.defaultdict(list)
    for e in ex:
        by[e[0]].append(e)
    keys = list(by)
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        sample = []
        for _k in range(len(keys)):
            sample.extend(by[keys[rng.randrange(len(keys))]])
        r2, h2 = tally(sample)
        vals.append(nstar(logistic_fit(sample), base_rate(r2, h2)))
    vals.sort()
    fit = lambda gg: 1 / (1 + math.exp(-(b[0] + b[1] * math.log(gg))))
    p(f'- {title}: logit h = {b[0]:.2f} {b[1]:+.2f}·ln g → h(1)={pc(fit(1))}, h(5)={pc(fit(5))}, '
      f'h(10)={pc(fit(10))}, h(15)={pc(fit(15))}, h(20)={pc(fit(20))}. 기준선(1~5년 실측 평균의 절반 {pc(base / 2)})과 만나는 g = **{ns:.1f}** '
      f'(조문 재표집 {B}회 95% {vals[int(0.025 * B)]:.1f}~{vals[int(0.975 * B) - 1]:.1f})')


def pool(sets, Y, n):
    out = set()
    for t in range(max(Y0, Y - n), Y):
        out |= sets[t]
    return out


def window_section(title, sets, targets, nmax=20, full_only=True):
    p(f'### {title}')
    p()
    p('| N | 쓴 목표 연도 | 출제 조문 | 적중 | 적중률 | 95% Wilson | 평균 풀 크기 | +적중(N−1→N) | +풀(평균) | 늘어난 조문 10개당 적중 |')
    p('|---|---|---|---|---|---|---|---|---|---|')
    prev = None
    rows = []
    for n in range(1, nmax + 1):
        ys = [Y for Y in targets if (Y - n >= Y0 or not full_only)]
        A = sum(len(sets[Y]) for Y in ys)
        H = sum(len(sets[Y] & pool(sets, Y, n)) for Y in ys)
        P = sum(len(pool(sets, Y, n)) for Y in ys)
        Hp = sum(len(sets[Y] & pool(sets, Y, n - 1)) for Y in ys) if n > 1 else 0
        Pp = sum(len(pool(sets, Y, n - 1)) for Y in ys) if n > 1 else 0
        dH, dP = H - Hp, P - Pp
        l, u = wilson(H, A)
        eff = 10 * dH / dP if dP else float('nan')
        yr = f'{ys[0]}–{ys[-1]} ({len(ys)})' if ys else '-'
        p(f'| {n} | {yr} | {A} | {H} | {pc(H / A)} | {pc(l)}–{pc(u)} | {P / len(ys):.1f} | {dH} | {dP / len(ys):.1f} | {eff:.2f} |')
        rows.append((n, ys, A, H, P, dH, dP))
    p()
    return rows


def per_year_table(sets, targets, ns):
    p('| Y | 출제 조문 | ' + ' | '.join(f'N={n} 적중/풀' for n in ns) + ' | 전체 이력 적중 |')
    p('|---|---|' + '---|' * len(ns) + '---|')
    for Y in targets:
        cells = []
        for n in ns:
            P = pool(sets, Y, n)
            cells.append(f'{len(sets[Y] & P)}/{len(P)}')
        allp = pool(sets, Y, 99)
        p(f'| {Y} | {len(sets[Y])} | ' + ' | '.join(cells) + f' | {len(sets[Y] & allp)} |')
    p()


# ================================================================== report
p('# 사시+변시 공법 사례형: 창 길이 N 분석 (자동 생성)')
p()
p('생성: `python3 -I analyze_sasi.py mapping.jsonl subq.jsonl <pilot>/mapping.jsonl out.md`. 표의 숫자는 모두 이 스크립트 출력이다.')
p()
p('## 0. 자료')
p()
c = collections.Counter((r['basis'], r['confidence']) for r in SASI)
p(f'- 사시 매핑 {len(SASI)}줄, 설문 {len(SUBQ)}개(사례 {sum(1 for s in SUBQ if s["qtype"] == "사례")}, 이론 {sum(1 for s in SUBQ if s["qtype"] == "이론")}).')
p('- 근거·신뢰도별: ' + ', '.join(f'{b}/{cf} {n}' for (b, cf), n in sorted(c.items())))
p(f'- 출제 당시 조문이 없어 현행 조문에 댄 법리 행: {sum(1 for r in SASI if r["article"] == "")}줄 (주 결과에서 제외).')
p(f'- 변시 시범 매핑 {sum(1 for r in PILOT if not r.get("overlay"))}줄 + 민감도 전용 보조 행 {len(OVERLAY)}줄.')
p()
MAIN = year_sets()
SAS = year_sets(src='sasi')
BS = year_sets(src='bs')
p('| 연도 | 사시 조문 | 변시 조문 | 합집합(주 결과) |')
p('|---|---|---|---|')
for Y in YEARS:
    p(f'| {Y} | {len(SAS[Y]) or ""} | {len(BS[Y]) or ""} | {len(MAIN[Y])} |')
p()

p('## 1. 재출제 위험률 h(g) — 주 결과 (발췌 제외·조 단위·현행 번호·사례 설문만)')
p()
p('h(g) = (마지막 출제 후 g년 된 조문 가운데 그해 다시 나온 수) / (그런 조문 수). 목표 연도 2003~2026 전부를 합쳤다. 2002년 이전 이력은 없으므로 2002년 이전에 나왔다가 2002년 이후 처음 보이는 조문은 \'새 조문\'으로 센다.')
p()
ex_main, risk_m, hit_m, base_m, res_m = hazard_section('1-1. 주 결과', MAIN)
logistic_section('로지스틱 평활(주 결과)', ex_main)
p()

p('## 2. 민감도')
p()
ex_s, *_ = hazard_section('2-1. \'확실\' 매핑만', year_sets(conf='sure'), show_1y=False)
logistic_section('로지스틱(확실만)', ex_s)
p()
ex_h, *_ = hazard_section('2-2. 항 단위', year_sets(unit='항'), show_1y=False)
logistic_section('로지스틱(항 단위)', ex_h)
p()
ex_t, *_ = hazard_section('2-3. 사시 이론 설문까지 포함', year_sets(theory=True), show_1y=False)
ex_pl, *_ = hazard_section('2-4. 법리 행(행정기본법 등 신설 전) 포함 + 변시 보조 행', year_sets(prelaw=True), show_1y=False)
ex_18, *_ = hazard_section('2-5. 목표 연도를 변시 단독 연도(2018~2026)로 한정', MAIN, targets=set(range(2018, 2027)), show_1y=False)
logistic_section('로지스틱(목표 2018~2026)', ex_18)
p()
ex_bs, *_ = hazard_section('2-6. 참고: 변시만(2012~2026, 시범 데이터 재계산)', BS, show_1y=False, boot=False)
ex_ss, *_ = hazard_section('2-7. 참고: 사시만(2002~2017)', SAS, show_1y=False, boot=False)

p('## 3. 법령별 h(g)')
p()
hazard_section('3-1. 헌법·헌법재판소법·행정소송법', MAIN, group=lambda k: k[0] in CORE3, show_1y=False)
hazard_section('3-2. 그 밖의 법령', MAIN, group=lambda k: k[0] not in CORE3, show_1y=False)
for law in ['헌법', '헌법재판소법', '행정소송법']:
    ex = exposures(MAIN, group=lambda k, law=law: k[0] == law)
    r, h = tally(ex)
    bands = band_rates(r, h, [(1, 5), (6, 10), (11, 15), (16, 24)])
    p(f'- {law}: ' + '; '.join(f'{a}~{b}년 {hh}/{rr} = {pc(hh / rr) if rr else "–"}' for a, b, hh, rr in bands))
p()

p('## 4. 창 길이 N 곡선')
p()
T5 = list(range(2022, 2027))
w_main = window_section('4-1. 목표 연도 2022~2026, 주 결과', MAIN, T5)
per_year_table(MAIN, T5, [5, 8, 9, 10, 11, 12, 15, 20])
window_section('4-2. 목표 연도 2022~2026, 확실만', year_sets(conf='sure'), T5)
window_section('4-3. 목표 연도 2022~2026, 항 단위', year_sets(unit='항'), T5)
window_section('4-4. 참고: 목표 연도 2017~2026 (N마다 창이 2002년 안으로 다 차는 해만)', MAIN, list(range(2017, 2027)))
window_section('4-5. 참고: 목표 연도 2017~2026, 확실만', year_sets(conf='sure'), list(range(2017, 2027)))

p('## 5. 8·9·10·11·12년 비교 (목표 2022~2026, 주 결과)')
p()
p('| N | 적중 | 적중률 | 평균 풀 | N=10 대비 적중 | N=10 대비 풀 |')
p('|---|---|---|---|---|---|')
ref = {r[0]: r for r in w_main}
for n in [5, 8, 9, 10, 11, 12, 15]:
    _, ys, A, H, P, _, _ = ref[n]
    _, _, _, H10, P10, _, _ = ref[10]
    p(f'| {n} | {H}/{A} | {pc(H / A)} | {P / len(ys):.1f} | {H - H10:+d} | {(P - P10) / len(ys):+.1f} |')
p()
OUT.close()
print('ok')
