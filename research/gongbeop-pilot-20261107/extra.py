"""Extra checks: excerpt recurrence, cluster bootstrap, law breakdown, hybrid rule.

Usage: python3 -I extra.py mapping.jsonl
"""
import collections
import json
import random
import sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
YEARS = range(2012, 2027)
MAIN = range(2022, 2027)


def k(r):
    a = r['current']['article'] if 'current' in r else r['article']
    return (r['law'], a)


core = [r for r in rows if r['basis'] != '문제지 발췌']
exc = [r for r in rows if r['basis'] == '문제지 발췌' and r['kind'] not in ('자치법규', '행정규칙')]

# 1. excerpt recurrence (조 단위, 법령명+조)
occ = collections.defaultdict(set)
for r in exc:
    occ[k(r)].add(r['year'])
print('1) 발췌 조문 중 두 해 이상 나온 것:', {f'{a} {b}': sorted(v) for (a, b), v in occ.items() if len(v) > 1})
laws = collections.defaultdict(set)
for r in exc:
    laws[r['law']].add(r['year'])
print('   발췌 법령 중 두 해 이상 나온 법령:', {a: sorted(v) for a, v in laws.items() if len(v) > 1})
core_keys = set(k(r) for r in core)
print('   발췌 조문이 다른 해의 비발췌(Claude/명시) 조문과 겹친 경우:',
      sorted(set(f'{a} {b}' for (a, b) in occ if (a, b) in core_keys)))

# sets per year and per subq
S = {y: set() for y in YEARS}
SQ = collections.defaultdict(lambda: collections.defaultdict(set))
for r in core:
    S[r['year']].add(k(r))
    SQ[r['year']][(r['q'], r['sub'])].add(k(r))


def pool(y, n, sets=S):
    out = set()
    for t in range(max(2012, y - n), y):
        out |= sets[t]
    return out


# 2. cluster bootstrap over 설문 within main years (pools fixed)
random.seed(1)
B = 5000
d = []
r5s, r10s = [], []
for _ in range(B):
    hA = h5 = h10 = 0
    for y in MAIN:
        subs = list(SQ[y].values())
        samp = [random.choice(subs) for _ in subs]
        A = set().union(*samp)
        p5, p10 = pool(y, 5), pool(y, 10)
        hA += len(A)
        h5 += len(A & p5)
        h10 += len(A & p10)
    d.append((h10 - h5) / hA)
    r5s.append(h5 / hA)
    r10s.append(h10 / hA)
for name, v in (('recall5', r5s), ('recall10', r10s), ('추가 적중 몫', d)):
    v.sort()
    print(f'2) 설문 단위 군집 부트스트랩 {name}: 중앙 {v[B // 2]:.2f}, 95% {v[int(B * .025)]:.2f}–{v[int(B * .975)]:.2f}')

# 3. law breakdown of main-year hits
cnt = collections.defaultdict(collections.Counter)
for y in MAIN:
    p5, p10, pall = pool(y, 5), pool(y, 10), pool(y, 99)
    for a in S[y]:
        cat = 'hit5' if a in p5 else ('extra10' if a in p10 else ('older' if a in pall else 'new'))
        cnt[a[0]][cat] += 1
print('3) 법령별 (Y=2022~2026, 조 단위) hit5 / extra10 / 11년+ / 처음 나옴')
for law, c in sorted(cnt.items(), key=lambda kv: -sum(kv[1].values())):
    print(f'   {law}: {c["hit5"]} / {c["extra10"]} / {c["older"]} / {c["new"]}')
newlist = collections.defaultdict(list)
for y in MAIN:
    pall = pool(y, 99)
    newlist[y] = sorted(f'{a} {b}' for a, b in S[y] if (a, b) not in pall)
print('   처음 나온 조문:', dict(newlist))

# 4. hybrid: 기본 3법 keep all history, others N=5  vs N=10
BASE = {'헌법', '헌법재판소법', '행정소송법'}
for label, base in (('헌법·헌재법·행소법 전부 유지 + 나머지 5년', BASE),
                    ('헌법만 전부 유지 + 나머지 5년', {'헌법'})):
    hA = h = ps = 0
    for y in MAIN:
        P = set(a for a in pool(y, 99) if a[0] in base) | set(a for a in pool(y, 5) if a[0] not in base)
        hA += len(S[y])
        h += len(S[y] & P)
        ps += len(P)
    print(f'4) {label}: recall {h}/{hA} = {h / hA:.0%}, 평균 풀 {ps / 5:.1f}')
hA = h = ps = 0
for y in MAIN:
    P = pool(y, 10)
    hA += len(S[y]); h += len(S[y] & P); ps += len(P)
print(f'   비교: 전체 10년 recall {h}/{hA} = {h / hA:.0%}, 평균 풀 {ps / 5:.1f}')

# 5. pool composition (how many in pool are 헌법 etc.)
for n in (5, 10):
    comp = collections.Counter()
    for y in MAIN:
        for a in pool(y, n):
            comp[a[0]] += 1
    print(f'5) 풀{n} 평균 구성:', {a: round(c / 5, 1) for a, c in comp.most_common()})

# 6. articles counted once (singletons) by law
occ2 = collections.defaultdict(set)
for r in core:
    occ2[k(r)].add(r['year'])
single = collections.Counter(a for (a, b), v in occ2.items() if len(v) == 1)
total = collections.Counter(a for (a, b) in occ2)
print('6) 법령별 서로 다른 조문 수(15년) / 한 해만 나온 조문 수:', {a: (total[a], single[a]) for a in total})
