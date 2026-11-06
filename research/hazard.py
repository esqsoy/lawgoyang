# 마지막 출제 후 g년 된 조문이 올해 다시 나올 비율(재출제 위험률). 발췌 제외, 조 단위, 현행 번호.
import json,sys,collections
rows=[json.loads(l) for l in open(sys.argv[1],encoding='utf-8')]
A=collections.defaultdict(set)
for r in rows:
    if r['basis']=='문제지 발췌': continue
    a=r.get('current') or r['article']
    A[r['year']].add((r['law'],str(a)))
ys=sorted(A); y0=ys[0]
risk=collections.Counter(); hit=collections.Counter()
for Y in ys[1:]:
    seen={}
    for y in ys:
        if y>=Y: break
        for k in A[y]: seen[k]=y
    for k,last in seen.items():
        g=Y-last; risk[g]+=1
        if k in A[Y]: hit[g]+=1
print(' g  위험  재출제  비율')
for g in sorted(risk): print(f'{g:>2} {risk[g]:>5} {hit[g]:>5}  {100*hit[g]/risk[g]:5.1f}%')
bands=[(1,2),(3,4),(5,6),(7,8),(9,10),(11,12),(13,14)]
print('묶음')
for a,b in bands:
    r=sum(risk[g] for g in range(a,b+1)); h=sum(hit[g] for g in range(a,b+1))
    if r: print(f'{a}~{b}년: {h}/{r} = {100*h/r:.1f}%')
r5=sum(risk[g] for g in range(1,6)); h5=sum(hit[g] for g in range(1,6))
print(f'1~5년 평균 {100*h5/r5:.1f}%')
