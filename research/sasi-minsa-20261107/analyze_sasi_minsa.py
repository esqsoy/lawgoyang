"""사시 2차 민법·민소(2003~2017) + 변시 민사법 사례형(2012~2026) 합집합 이력으로
재출제 위험률 h(g)와 창 길이 N 곡선을 계산한다.

Usage: python3 -I analyze_sasi_minsa.py SASI.jsonl SASI_subq.jsonl SASI_meta.json BYUN.jsonl BYUN_meta.json OUT.md

주 결과: 발췌 제외 · 조 단위 · 현행 번호 · 사시 '이론' 설문 제외 · 2012~2017은 사시∪변시.
"""
import collections
import json
import math
import sys

SASI = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
SUBQ = [json.loads(l) for l in open(sys.argv[2], encoding='utf-8')]
SMETA = json.load(open(sys.argv[3], encoding='utf-8'))
BYUN = [json.loads(l) for l in open(sys.argv[4], encoding='utf-8')]
BMETA = json.load(open(sys.argv[5], encoding='utf-8'))
OUT = open(sys.argv[6], 'w', encoding='utf-8')

for i, r in enumerate(SASI):
    r['_src'] = '사시'
for i, r in enumerate(BYUN):
    r['_src'] = '변시'
SB = {i: n for i, n in SMETA['bundle_rows']}
BB = {i: n for i, n in BMETA['bundle_rows']}
for i, r in enumerate(SASI):
    r['_bundle'] = SB.get(i)
for i, r in enumerate(BYUN):
    r['_bundle'] = BB.get(i)
QTYPE = {(s['year'], s['part'], s['q'], s['sub']): s['qtype'] for s in SUBQ}
for r in SASI:
    r['_qtype'] = QTYPE[(r['year'], r['part'], r['q'], r['sub'])]
for r in BYUN:
    r['_qtype'] = '사례'
ALL = SASI + BYUN
YEARS = list(range(2003, 2027))
TARGETS = list(range(2022, 2027))


def p(*a):
    print(*a, file=OUT)


def key(r):
    law, art = r['law'], r['article']
    cur = r.get('current')
    if cur == '없음':
        return None
    if isinstance(cur, dict):
        law = cur.get('law', law)
        art = cur['article']
    return (law, art)


def artno(a):
    d = ''.join(ch for ch in a.split('의')[0] if ch.isdigit())
    return int(d) if d else 0


def civil_book(a):
    n = artno(a)
    if n <= 184:
        return '총칙'
    if n <= 372:
        return '물권'
    if n <= 766:
        return '채권'
    if n <= 996:
        return '친족'
    return '상속'


def year_sets(sure=False, nobundle=False, theory=False, law=None, book=None, src=None):
    sets = {y: set() for y in YEARS}
    for r in ALL:
        if r['basis'] == '문제지 발췌':
            continue
        if not theory and r['_qtype'] == '이론':
            continue
        if sure and r['confidence'] != '확실':
            continue
        if nobundle and r['_bundle']:
            continue
        if src and r['_src'] != src:
            continue
        k = key(r)
        if k is None:
            continue
        if law == '기타':
            if k[0] in ('민법', '민사소송법', '민사집행법'):
                continue
        elif law and k[0] != law:
            continue
        if book and (k[0] != '민법' or civil_book(k[1]) != book):
            continue
        sets[r['year']].add(k)
    return sets


def wilson(h, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = h / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    m = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (max(0.0, (c - m) / d), min(1.0, (c + m) / d))


def hazard(sets, target_min=2004, target_max=2026):
    risk = collections.Counter()
    hit = collections.Counter()
    for Y in range(max(target_min, 2004), target_max + 1):
        last = {}
        for y in range(2003, Y):
            for k in sets[y]:
                last[k] = y
        for k, L in last.items():
            g = Y - L
            risk[g] += 1
            if k in sets[Y]:
                hit[g] += 1
    return risk, hit


def bands(risk, hit, width=2, gmax=24):
    out = []
    for a in range(1, gmax + 1, width):
        b = a + width - 1
        n = sum(risk[g] for g in range(a, b + 1))
        h = sum(hit[g] for g in range(a, b + 1))
        out.append((a, b, h, n))
    return out


def base15(risk, hit):
    n = sum(risk[g] for g in range(1, 6))
    h = sum(hit[g] for g in range(1, 6))
    return h, n


RULE_EXTRA = {}


def fmt(h, n):
    if n == 0:
        return '— (0)'
    lo, hi = wilson(h, n)
    return f'{100 * h / n:.1f}% ({h}/{n}) [{100 * lo:.0f}–{100 * hi:.0f}]'


def rule(risk, hit, width=2):
    h5, n5 = base15(risk, hit)
    base = h5 / n5 if n5 else float('nan')
    half = base / 2
    last_pt = None
    last_up = None
    first_below = None
    last_pt50 = None
    first_sure_below = None
    for a, b, h, n in bands(risk, hit, width):
        if n == 0:
            continue
        r = h / n
        lo, hi = wilson(h, n)
        if r >= half:
            last_pt = (a, b)
            if n >= 50:
                last_pt50 = (a, b)
        if hi >= half:
            last_up = (a, b)
        if r < half and first_below is None:
            first_below = (a, b)
        if hi < half and first_sure_below is None:
            first_sure_below = (a, b)
    RULE_EXTRA[id(risk)] = (last_pt50, first_sure_below)
    return base, last_pt, last_up, first_below


def hazard_table(title, sets, width=2, show_1y=False, target_min=2004, target_max=2026):
    risk, hit = hazard(sets, target_min, target_max)
    p(f'### {title}')
    p()
    h5, n5 = base15(risk, hit)
    base, last_pt, last_up, first_below = rule(risk, hit, width)
    p(f'1~5년 평균 {fmt(h5, n5)} → 절반 기준 {100 * base / 2:.1f}%')
    p()
    p('| g(년) | 위험률 (재출제/위험) [Wilson 95%] | 절반 이상? |')
    p('|---|---|---|')
    for a, b, h, n in bands(risk, hit, width):
        if n == 0:
            continue
        lab = f'{a}' if a == b else f'{a}~{b}'
        ok = '예' if h / n >= base / 2 else '아니오'
        p(f'| {lab} | {fmt(h, n)} | {ok} |')
    p()
    lp = f'{last_pt[0]}~{last_pt[1]}년' if last_pt else '없음'
    lu = f'{last_up[0]}~{last_up[1]}년' if last_up else '없음'
    fb = f'{first_below[0]}~{first_below[1]}년' if first_below else '없음'
    p(f'- 잣대(점추정이 절반 이상인 마지막 묶음): **{lp}** / 상한이 절반 이상인 마지막 묶음: {lu} / 처음 절반 아래로 떨어진 묶음: {fb}')
    x50, xs = RULE_EXTRA[id(risk)]
    ff = lambda x: f'{x[0]}~{x[1]}년' if x else '없음'
    p(f'- 보조: 위험 50건 이상 묶음만 볼 때 절반 이상인 마지막 묶음: {ff(x50)} / 구간 상한까지 절반 아래인 첫 묶음: {ff(xs)}')
    p()
    if show_1y:
        p('<details><summary>1년 단위</summary>')
        p()
        p('| g | 위험 | 재출제 | 비율 | Wilson 95% |')
        p('|---|---|---|---|---|')
        for g in range(1, 25):
            n, h = risk[g], hit[g]
            if n == 0:
                p(f'| {g} | 0 | 0 | — | — |')
                continue
            lo, hi = wilson(h, n)
            p(f'| {g} | {n} | {h} | {100 * h / n:.1f}% | {100 * lo:.0f}–{100 * hi:.0f}% |')
        p()
        p('</details>')
        p()
    return risk, hit, (base, last_pt, last_up, first_below) + RULE_EXTRA[id(risk)]


def pool(sets, Y, N):
    s = set()
    for y in range(Y - N, Y):
        s |= sets.get(y, set())
    return s


def ncurve(sets, nmax=20):
    res = []
    for N in range(1, nmax + 1):
        H = T = P = 0
        for Y in TARGETS:
            pl = pool(sets, Y, N)
            H += len(sets[Y] & pl)
            T += len(sets[Y])
            P += len(pl)
        res.append((N, H, T, P))
    return res


def ncurve_table(title, sets, nmax=20):
    res = ncurve(sets, nmax)
    p(f'### {title}')
    p()
    p('| N | 적중(2022~26 합) | 적중률 | 평균 풀(조) | N-1→N 늘어난 조문 | 늘어난 조문 1개당 적중 | 3칸 평활(N-2→N+1) |')
    p('|---|---|---|---|---|---|---|')
    prev = None
    for i, (N, H, T, P) in enumerate(res):
        if prev:
            dH, dP = H - prev[1], P - prev[3]
            m = f'{dP / 5:.1f}' if dP else '0'
            mm = f'{dH / dP:.3f}' if dP else '—'
        else:
            m, mm = '—', f'{H / P:.3f}' if P else '—'
        sm = '—'
        if i >= 2 and i + 1 < len(res):
            dH = res[i + 1][1] - res[i - 2][1]
            dP = res[i + 1][3] - res[i - 2][3]
            sm = f'{dH / dP:.3f}' if dP else '—'
        p(f'| {N} | {H}/{T} | {100 * H / T:.1f}% | {P / 5:.0f} | {m} | {mm} | {sm} |')
        prev = (N, H, T, P)
    p()
    return res


# ------------------------------------------------------------------ 출력
main = year_sets()
p('# 사시 2차 민법·민소 + 변시 민사: 재출제 위험률과 창 길이 N (자동 생성)')
p()
p('주 결과 정의: 발췌 제외 · 조 단위 · 현행 번호 · 사시 이론 설문 제외 · 2012~2017은 사시∪변시 합집합. '
  '위험률 h(g)=마지막 출제 후 g년 된 조문 중 그해 다시 나온 비율(목표 연도 2004~2026). Wilson 95% 구간.')
p()
p('## 0. 자료 규모')
p()
nsq = collections.Counter((s['part'], s['qtype']) for s in SUBQ)
p(f'- 사시 매핑 {len(SASI)}줄, 설문 {len(SUBQ)}개: ' + ', '.join(f'{k[0]} {k[1]} {v}' for k, v in sorted(nsq.items())))
cc = collections.Counter(r['confidence'] for r in SASI)
p(f'- 사시 신뢰도: 확실 {cc["확실"]}, 확인 필요 {cc["확인 필요"]} ({100 * cc["확인 필요"] / len(SASI):.0f}%); 묶음 줄 {len(SB)}')
p(f'- 변시 매핑 {len(BYUN)}줄(발췌 {sum(1 for r in BYUN if r["basis"] == "문제지 발췌")}), 묶음 줄 {len(BB)}')
p()
p('| 연도 | 사시 조 | 변시 조 | 합집합 조 |')
p('|---|---|---|---|')
ss, bs = year_sets(src='사시'), year_sets(src='변시')
for y in YEARS:
    p(f'| {y} | {len(ss[y]) or ""} | {len(bs[y]) or ""} | {len(main[y])} |')
p()

p('## 1. 재출제 위험률 h(g) — 주 결과')
p()
R1 = hazard_table('1-1. 2년 묶음 (목표 연도 2004~2026 전체)', main, 2, show_1y=True)
R1b = hazard_table('1-2. 목표 연도 2018~2026만 (변시 단독 시기: 앞으로 쓰일 상황과 같음)', main, 2, target_min=2018)
R1c = hazard_table('1-3. 목표 연도 2004~2017만 (사시 시기)', main, 2, target_max=2017)
R1d = hazard_table('1-4. 3년 묶음 (전체)', main, 3)

p('## 2. 같은 계산의 변형')
p()
R2a = hazard_table('2-1. 확실만', year_sets(sure=True), 2)
R2b = hazard_table('2-2. 묶음 줄 제외(하한)', year_sets(nobundle=True), 2)
R2c = hazard_table('2-3. 확실만 + 묶음 제외', year_sets(sure=True, nobundle=True), 2)
R2d = hazard_table('2-4. 사시 이론 설문 포함', year_sets(theory=True), 2)
R2e = hazard_table('2-5. 변시만(앞선 시범과 같은 자료, 대조용)', year_sets(src='변시'), 2)
R2f = hazard_table('2-6. 사시만(사시→사시, 목표 2004~2017)', year_sets(src='사시'), 2, show_1y=True, target_max=2017)


def hazard_table_pooled(title, parts, width=2):
    risk = collections.Counter(); hit = collections.Counter()
    for sets, tmin, tmax in parts:
        r_, h_ = hazard(sets, tmin, tmax)
        risk.update(r_); hit.update(h_)
    p(f'### {title}')
    p()
    h5, n5 = base15(risk, hit)
    base, last_pt, last_up, first_below = rule(risk, hit, width)
    p(f'1~5년 평균 {fmt(h5, n5)} → 절반 기준 {100 * base / 2:.1f}%')
    p()
    p('| g(년) | 위험률 [Wilson 95%] | 절반 이상? |')
    p('|---|---|---|')
    for a_, b_, h, n in bands(risk, hit, width):
        if n == 0:
            continue
        p(f"| {a_}~{b_} | {fmt(h, n)} | {'예' if h / n >= base / 2 else '아니오'} |")
    p()
    x50, xs = RULE_EXTRA[id(risk)]
    f = lambda x: f'{x[0]}~{x[1]}년' if x else '없음'
    p(f'- ① {f(last_pt)} / ② {f(x50)} / ③ {f(first_below)} / ④ {f(xs)}')
    p()
    return risk, hit, (base, last_pt, last_up, first_below, x50, xs)


R2g = hazard_table_pooled('2-7. 같은 시험 안에서만(사시→사시 목표 2004~17 + 변시→변시 목표 2013~26 합산)',
                          [(year_sets(src='사시'), 2004, 2017), (year_sets(src='변시'), 2013, 2026)])
R2h = hazard_table_pooled('2-8. 같은 시험 안에서만, 확실만',
                          [(year_sets(src='사시', sure=True), 2004, 2017), (year_sets(src='변시', sure=True), 2013, 2026)])
R2i = hazard_table_pooled('2-9. 같은 시험 안에서만, 묶음 제외',
                          [(year_sets(src='사시', nobundle=True), 2004, 2017), (year_sets(src='변시', nobundle=True), 2013, 2026)])

p('## 3. 법령별·민법 편별 h(g)')
p()
LAWR = {}
for law in ('민법', '민사소송법', '민사집행법'):
    LAWR[law] = hazard_table(f'3. {law}', year_sets(law=law), 2)
BOOKR = {}
for bk in ('총칙', '물권', '채권', '친족', '상속'):
    BOOKR[bk] = hazard_table(f'3. 민법 {bk}', year_sets(law='민법', book=bk), 2)

p('## 4. 창 길이 N 곡선 (목표 2022~2026)')
p()
p('풀 = 목표 연도 직전 N년(Y-N ~ Y-1)에 나온 조문 합집합. 적중률 = 그해 조문 중 풀에 있던 비율. '
  '2022년은 N=20이면 2002년(자료 없음)까지 들어가 사실상 N=19.')
p()
NC = ncurve_table('4-1. 주 결과', main)
NCs = ncurve_table('4-2. 확실만', year_sets(sure=True))
NCb = ncurve_table('4-3. 묶음 제외(하한)', year_sets(nobundle=True))
NCt = ncurve_table('4-4. 이론 포함', year_sets(theory=True))
NCv = ncurve_table('4-5. 변시 이력만 쓴 경우(대조: 사시를 붙이기 전)', year_sets(src='변시'), 14)
LAWN = {}
for law in ('민법', '민사소송법', '민사집행법'):
    LAWN[law] = ncurve_table(f'4-6. {law}', year_sets(law=law))
BOOKN = {}
for bk in ('총칙', '물권', '채권', '친족', '상속'):
    BOOKN[bk] = ncurve_table(f'4-7. 민법 {bk}', year_sets(law='민법', book=bk))

p('## 5. N=8~12 요약 (주 결과)')
p()
p('| N | 적중률 | 평균 풀 | N-1→N 1개당 적중 | 확실만 적중률 | 묶음 제외 적중률 |')
p('|---|---|---|---|---|---|')
for N in range(6, 16):
    a = NC[N - 1]
    pr = NC[N - 2]
    m = (a[1] - pr[1]) / (a[3] - pr[3]) if a[3] != pr[3] else float('nan')
    s_ = NCs[N - 1]
    b_ = NCb[N - 1]
    p(f'| {N} | {100 * a[1] / a[2]:.1f}% | {a[3] / 5:.0f} | {m:.3f} | {100 * s_[1] / s_[2]:.1f}% | {100 * b_[1] / b_[2]:.1f}% |')
p()

p('## 6. 잣대 요약')
p()
p('| 계산 | 1~5년 평균 | ① 절반 이상 마지막 묶음(문자 그대로) | ② ①을 위험 50건 이상 묶음으로 한정 | ③ 처음 절반 아래(점) | ④ 상한까지 절반 아래인 첫 묶음 | 상한 기준 마지막 |')
p('|---|---|---|---|---|---|---|')


def rr(name, R):
    base, lp, lu, fb, l50, fsb = R[2]
    f = lambda x: f'{x[0]}~{x[1]}' if x else '없음'
    p(f'| {name} | {100 * base:.1f}% | {f(lp)} | {f(l50)} | {f(fb)} | {f(fsb)} | {f(lu)} |')


rr('주 결과(전체)', R1)
rr('목표 2018~26', R1b)
rr('목표 2004~17', R1c)
rr('3년 묶음', R1d)
rr('확실만', R2a)
rr('묶음 제외', R2b)
rr('확실+묶음 제외', R2c)
rr('이론 포함', R2d)
rr('변시만', R2e)
rr('사시만(목표 2004~17)', R2f)
rr('같은 시험 안(사시+변시 합산)', R2g)
rr('같은 시험 안, 확실만', R2h)
rr('같은 시험 안, 묶음 제외', R2i)
for k, v in LAWR.items():
    rr(k, v)
for k, v in BOOKR.items():
    rr('민법 ' + k, v)
p()


p('## 8. 법령별로 N을 달리할 때 (목표 2022~2026, 주 결과)')
p()
p('민법·민소·나머지(민집·특별법)에 서로 다른 N. 적중·풀은 5개 목표 연도 합/평균.')
p()
LS = {'민법': year_sets(law='민법'), '민사소송법': year_sets(law='민사소송법'),
      '나머지': {y: year_sets(law='민사집행법')[y] | year_sets(law='기타')[y] for y in YEARS}}
def hp(sets, N):
    H = T = P = 0
    for Y in TARGETS:
        pl = pool(sets, Y, N)
        H += len(sets[Y] & pl); T += len(sets[Y]); P += len(pl)
    return H, T, P
p('| 민법 N | 민소 N | 나머지 N | 적중 | 적중률 | 평균 풀 |')
p('|---|---|---|---|---|---|')
for nm, ns, no in [(6, 6, 6), (8, 8, 8), (10, 10, 10), (12, 12, 12), (6, 10, 6), (6, 12, 6), (8, 10, 8), (8, 12, 8),
                   (8, 15, 8), (10, 12, 10), (10, 15, 10)]:
    H = T = P = 0
    for law, N in (('민법', nm), ('민사소송법', ns), ('나머지', no)):
        h, t_, p_ = hp(LS[law], N)
        H += h; T += t_; P += p_
    p(f'| {nm} | {ns} | {no} | {H}/{T} | {100 * H / T:.1f}% | {P / 5:.0f} |')
p()
p('## 7. 진단')
p()
p('### 7-1. 목표 2018~2026: 마지막 출제가 변시였던 조문 vs 사시에만 나왔던 조문')
p()
p('마지막 출제 연도가 2012~2017(두 시험 공존)인 조문만 비교. 그해 변시에 나왔으면 "변시", 사시에만 나왔으면 "사시만".')
p()
ss_, bs_ = year_sets(src='사시'), year_sets(src='변시')
rk = collections.Counter(); ht = collections.Counter()
for Y in range(2018, 2027):
    last = {}
    for y in range(2003, Y):
        for k in main[y]:
            last[k] = y
    for k, L in last.items():
        if not (2012 <= L <= 2017):
            continue
        src = '변시' if k in bs_[L] else '사시만'
        g = Y - L
        band = '1~4' if g <= 4 else ('5~8' if g <= 8 else ('9~12' if g <= 12 else '13~'))
        rk[(src, band)] += 1
        if k in main[Y]:
            ht[(src, band)] += 1
p('| g | 마지막이 변시 | 마지막이 사시만 |')
p('|---|---|---|')
for band in ('1~4', '5~8', '9~12', '13~'):
    p(f"| {band} | {fmt(ht[('변시', band)], rk[('변시', band)])} | {fmt(ht[('사시만', band)], rk[('사시만', band)])} |")
p()
p('### 7-2. 목표 연도 조문 중 2003년 이후 한 번도 안 나왔던 조문(어떤 N으로도 못 잡음)')
p()
p('| 목표 연도 | 조문 수 | 처음 나온 조문 | 비율 |')
p('|---|---|---|---|')
tn = tt = 0
for Y in TARGETS:
    seen = set()
    for y in range(2003, Y):
        seen |= main[y]
    new = main[Y] - seen
    tn += len(new); tt += len(main[Y])
    p(f'| {Y} | {len(main[Y])} | {len(new)} | {100 * len(new) / len(main[Y]):.0f}% |')
p(f'| 합 | {tt} | {tn} | {100 * tn / tt:.0f}% |')
p()
p('### 7-3. 목표 2022~2026 적중 조문의 "직전 출제 간격" 분포(주 결과)')
p()
gaps = collections.Counter()
for Y in TARGETS:
    for k in main[Y]:
        L = None
        for y in range(Y - 1, 2002, -1):
            if k in main[y]:
                L = y
                break
        gaps['처음' if L is None else Y - L] += 1
p('| 직전 출제 후 년수 | 조문 수 |')
p('|---|---|')
for g in sorted([x for x in gaps if x != '처음']):
    p(f'| {g} | {gaps[g]} |')
p(f"| 처음(2003 이후 없음) | {gaps['처음']} |")
p()
p('### 7-4. 사시에서 g≥9년 만에 다시 나온 조문 목록(주 결과, 목표 2004~2026)')
p()
p('| 목표 연도 | 조문 | 직전 출제 | 간격 |')
p('|---|---|---|---|')
for Y in range(2004, 2027):
    for k in sorted(main[Y]):
        L = None
        for y in range(Y - 1, 2002, -1):
            if k in main[y]:
                L = y
                break
        if L is not None and Y - L >= 9:
            p(f'| {Y} | {k[0]} {k[1]}조 | {L} | {Y - L} |')
p()
OUT.close()
