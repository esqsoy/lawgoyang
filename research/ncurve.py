# 공법+민사(변시) 합쳐서: 창 N별 적중률·평균 풀·늘어난 조문 1개당 적중, 그리고 g년 위험률(합산)
import json,sys,collections
A={}
for name,path in (('공법',sys.argv[1]),('민사',sys.argv[2])):
    d=collections.defaultdict(set)
    for l in open(path,encoding='utf-8'):
        r=json.loads(l)
        if r['basis']=='문제지 발췌': continue
        a=r.get('current') or r['article']
        if isinstance(a,(list,tuple)): a=a[0]
        d[r['year']].add((r['law'],str(a)))
    A[name]=d
def pool(d,Y,N):
    s=set()
    for y in range(Y-N,Y): s|=d.get(y,set())
    return s
Ys=range(2022,2027)
print('N | 공법 적중·풀 | 민사 적중·풀 | 합 적중률 | 합 평균풀 | N-1→N 늘어난 조문 1개당 다음해 적중')
prev=None
for N in range(1,11):
    row=[];H=T=P=0
    for name in ('공법','민사'):
        d=A[name];h=sum(len(d[Y]&pool(d,Y,N)) for Y in Ys);t=sum(len(d[Y]) for Y in Ys);p=sum(len(pool(d,Y,N)) for Y in Ys)/5
        row.append(f'{h}/{t}·{p:.0f}');H+=h;T+=t;P+=p
    m=''
    if prev: m=f'{(H-prev[0])/((P-prev[1])*5):.3f}'
    print(f'{N:>2} | {row[0]} | {row[1]} | {100*H/T:.0f}% | {P:.0f} | {m}')
    prev=(H,P)
