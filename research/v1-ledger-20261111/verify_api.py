"""v1 매핑의 조·항이 오늘 시행 중인 법령(Open API, target=eflaw)에 실제로 있는지 대조한다.

usage: python3 -I verify_api.py <cache 폴더> <out.json>
- research/v1-*-20261111/mapping.jsonl 의 줄 가운데 '문제지 발췌'를 뺀 줄을 본다(이론 설문 줄도 본다).
- 번호는 `current`가 있으면 그것(현행 번호), 없으면 article/para.
- 문제 종류: 법령 없음 / 조 없음 / 삭제된 조 / 항 없음(항 번호가 그 조의 항 수를 넘음, 또는 항이 없는 조에 항 번호).
- 법령 전체 응답은 cache에 둔다(pipeline/fetch_api.py와 같은 캐시).
"""
import glob
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fetch_api', ROOT / 'pipeline' / 'fetch_api.py')
fa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fa)

cache, out = sys.argv[1], sys.argv[2]
laws = {}


def law_doc(name):
    if name not in laws:
        try:
            cur = fa.find_current(name)
            laws[name] = fa.shape_law(fa.fetch_full(cur, cache))
            laws[name]['ef'] = cur['ef']
        except Exception as err:  # 현행 법령이 없거나 이름이 다름
            laws[name] = {'error': str(err)}
    return laws[name]


def numbered(a):
    return [p['no'] for p in a['paras'] if isinstance(p.get('no'), int)]


problems = defaultdict(list)
checked = Counter()
for f in sorted(glob.glob(str(ROOT / 'research' / 'v1-*-20261111' / 'mapping.jsonl'))):
    folder = Path(f).parent.name
    for line in open(f, encoding='utf-8'):
        r = json.loads(line)
        if r['basis'] == '문제지 발췌':
            continue
        cur = r.get('current')
        if cur == '없음':
            continue
        law, art, para = r['law'], str(r.get('article') or ''), str(r.get('para') or '')
        if isinstance(cur, dict):
            law, art, para = cur.get('law') or law, str(cur.get('article') or ''), str(cur.get('para') or '')
        if not art:
            continue
        checked[folder] += 1
        where = f"{r['year']} {r['part']} {r['q']}-{r['sub']}"
        d = law_doc(law)
        if 'error' in d:
            problems[folder].append({'kind': '법령 없음', 'law': law, 'article': art, 'para': para, 'where': where, 'note': d['error']})
            continue
        a = d['articles'].get(art)
        if a is None:
            problems[folder].append({'kind': '조 없음', 'law': law, 'article': art, 'para': para, 'where': where})
            continue
        body = ' '.join(p.get('text', '') for p in a['paras'])
        if body.strip().startswith('삭제'):
            problems[folder].append({'kind': '삭제된 조', 'law': law, 'article': art, 'para': para, 'where': where})
            continue
        if para:
            nums = numbered(a)
            if not para.isdigit():
                problems[folder].append({'kind': '항 표기 이상', 'law': law, 'article': art, 'para': para, 'where': where})
            elif not nums:
                problems[folder].append({'kind': '항 없는 조에 항 번호', 'law': law, 'article': art, 'para': para, 'where': where})
            elif int(para) not in nums:
                problems[folder].append({'kind': '항 없음', 'law': law, 'article': art, 'para': para, 'where': where,
                                         'note': f'이 조의 항: {nums[0]}~{nums[-1]}'})

report = {'checked': dict(checked), 'problems': problems,
          'laws': {k: v.get('ef', v.get('error')) for k, v in sorted(laws.items())}}
Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
for folder in sorted(checked):
    ps = problems.get(folder, [])
    print(f"{folder}: {checked[folder]}줄 대조, 문제 {len(ps)}", dict(Counter(p['kind'] for p in ps)))
