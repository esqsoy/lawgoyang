"""python3 -I pipeline/tests/shape_test.py — 조문 원문 나누기(fetch_web.shape) 검사.
목 아래 세목(1) 2) 3))을 항으로 자르지 않고 목 아래에 둔다(26.11.08, 행정기본법 제2조에서 드러난 버그)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_web as F

lines = ['제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.',
         '1. “법령등”이란 다음 각 목의 것을 말한다.',
         '가. 법령: 다음의 어느 하나에 해당하는 것',
         '1) 법률 및 대통령령ㆍ총리령ㆍ부령',
         '2) 국회규칙ㆍ대법원규칙',
         '3) 1) 또는 2)의 위임을 받아 정한 고시',
         '나. 자치법규: 지방자치단체의 조례 및 규칙',
         '2. “행정청”이란 다음 각 목의 자를 말한다.']
d = F.shape(lines, '2')
assert d['title'] == '정의'
assert len(d['paras']) == 1, d['paras']
ho = d['paras'][0]['ho']
assert [h['no'] for h in ho] == ['1', '2']
mok = ho[0]['mok']
assert [m['no'] for m in mok] == ['가', '나']
assert [s['no'] for s in mok[0]['sub']] == ['1', '2', '3']
assert mok[0]['sub'][2]['text'].startswith('1) 또는 2)의 위임을 받아')
print('shape ok: 세목 1)~3)이 가목 아래, 나목과 제2호도 제자리')
