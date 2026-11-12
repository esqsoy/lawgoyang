#!/usr/bin/env python3
"""기출 조문 원장 v0을 조립한다: research/의 매핑 네 개 → data/ledger/ledger-v0.json, sets-v0.json.

사용: python3 -I pipeline/ledger.py        # v0 → ledger-v0.json, sets-v0.json (게임·직검수 페이지가 읽는다)
      python3 -I pipeline/ledger.py --v1   # v1 → ledger-v1.json, sets-v1.json
- v0은 변호사시험(공법·민사 사례형 2012~2026)과 사법시험 2차(공법 2002~2017, 민사 2003~2017)만 담는다.
  매핑은 Claude가 했고 영신 검수 전이다.
- v1은 v0에 법무사·법원행정고시·5급 공채·입법고시·노무사·변리사·감정평가사 2017~2026 매핑(research/v1-*-20261111)을
  더한다(26.11.11). 시험 글자는 과목 이름 앞머리로 정한다(exam_of).
- 규칙(PRINCIPLES 1, 설계안 A1·A4):
  · 문제지 발췌 조문(시험장에서 붙여 주는 개별법)은 넣지 않는다.
  · 현행 번호로 센다. 현행에 없는 조문('없음')과 현행 조문을 대지 못한 법리 행은 원장 밖(retired)에 둔다.
  · 창은 최근 10개 연도(지금 2017~2026). 창 안에 한 번이라도 나오면 외울 조문, 아니면 보관함.
  · 빈출도는 시험 한 글자 + 창 안에서 나온 해(회차) 수: 변8 사1.
  · 사시의 '이론' 설문(subq.jsonl qtype)은 사례형이 아니라서 뺀다.
- sets-v0.json: 세트 = 기출 한 문(시험·연도·과목·문), 최근 회차부터. 카드 = 그 문의 (설문, 조문) 하나.
- data/sets/에 쓴 세트가 있으면 그 문은 세트의 근거 조문으로 센다(원장 매핑을 대신한다).
- later: 판례 층·학설 층으로 미룬 것(세트의 later, 카드 해설의 '판례 법리' 메모). 데이터로만 두고 빈출도에 세지 않는다(PRINCIPLES 1-2).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / 'research'
WINDOW = (2017, 2026)
EXAM = {'변': '변호사시험', '사': '사법시험'}
STAGES = ['초안', '원문 대조', '확인 필요 분류', '바탕 판결', '영신 직검수']  # build.py와 같게(PRINCIPLES 1-2)
SOURCES = [
    ('gongbeop-pilot-20261107', None),
    ('minsa-pilot-20261107', None),
    ('sasi-gongbeop-20261107', 'subq.jsonl'),
    ('sasi-minsa-20261107', 'subq.jsonl'),
]
# v1(`--v1`): 나머지 일곱 시험 2017~2026 매핑을 더한다(26.11.11). 글자 배정은 설계안 A4 추천(design/proposal-20261107.md).
EXAM_V1 = {'변': '변호사시험', '사': '사법시험', '노': '공인노무사', '법': '법무사', '리': '변리사',
           '원': '법원행정고시', '행': '5급 공채', '입': '입법고시', '감': '감정평가사'}
SOURCES_V1 = SOURCES + [
    ('v1-beopmusa-20261111', 'subq.jsonl'),
    ('v1-beopmusa-seoryu-20261111', 'subq.jsonl'),
    ('v1-beophaeng-20261111', 'subq.jsonl'),
    ('v1-5geup-20261111', 'subq.jsonl'),
    ('v1-ipbeop-20261111', 'subq.jsonl'),
    ('v1-nomusa-20261111', 'subq.jsonl'),
    ('v1-byeonrisa-20261111', 'subq.jsonl'),
    ('v1-gampyeong-20261111', 'subq.jsonl'),
]
PART_PREFIX = [('사시', '사'), ('법무사', '법'), ('법원행정고시', '원'), ('5급 공채', '행'), ('입법고시', '입'),
               ('노무사', '노'), ('변리사', '리'), ('감정평가사', '감')]


def exam_of(part):
    """과목 이름 앞머리로 시험 글자를 정한다. 변호사시험 매핑은 과목 이름에 시험명이 없다('민사법', '공법')."""
    for prefix, e in PART_PREFIX:
        if part.startswith(prefix):
            return e
    return '변'


def load(p):
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]


def now_number(r):
    """현행 법령명·조·항. 현행에 없으면 None."""
    cur = r.get('current')
    if cur == '없음':
        return None
    if isinstance(cur, dict):
        a = str(cur.get('article') or '')
        if not a:
            return None
        return cur.get('law') or r['law'], a, str(cur.get('para') or ''), cur.get('note', '')
    if not str(r.get('article') or ''):
        return None
    return r['law'], str(r['article']), str(r.get('para') or ''), ''


def cur_of(x):
    """조 칸이 빈 줄(출제 당시 없던 조문)은 current의 조·항까지 열쇠에 넣어 같은 설문의 줄을 가른다."""
    if not str(x.get('article') or '') and isinstance(x.get('current'), dict):
        return str(x['current'].get('article') or ''), str(x['current'].get('para') or '')
    return '', ''


def rkey(x):
    """검토(review.jsonl)·고침(corrections.jsonl)이 매핑 줄을 찾는 열쇠."""
    return (x['year'], x['part'], str(x['q']), str(x['sub']), x['law'], str(x.get('article') or ''), str(x.get('para') or ''), cur_of(x))


def main():
    v1 = '--v1' in sys.argv
    ver, exams, sources = ('v1', EXAM_V1, SOURCES_V1) if v1 else ('v0', EXAM, SOURCES)
    hits, retired = [], []
    for folder, subq in sources:
        rows = load(R / folder / 'mapping.jsonl')
        # 검토 결과(review.jsonl, 26.11.12~): 원문(Open API) 대조 뒤 '확인 필요' 줄을 다시 판단한 것. 같은 줄의 확신도를 바꾼다.
        rv = R / folder / 'review.jsonl'
        if rv.exists():
            review = {rkey(x): x for x in load(rv)}
            for r in rows:
                x = review.get(rkey(r))
                if x and x.get('confidence') in ('확실', '확인 필요'):
                    r['confidence'] = x['confidence']
            # 고침(corrections.jsonl, 26.11.12~): 두 검토가 합의한 매핑 고침. replace(조·항 바꾸기)·drop(줄 지우기)·add(줄 더하기).
            cv = R / folder / 'corrections.jsonl'
            if cv.exists():
                for c in load(cv):
                    if c['action'] == 'add':
                        n = c['new']
                        law = n['law']
                        kind = ('헌법' if law == '헌법' else '대통령령' if law.endswith('시행령') else '부령' if law.endswith('시행규칙')
                                else '대법원규칙' if law.endswith('규칙') else '법률')
                        rows.append({'year': c['year'], 'round': c.get('round'), 'part': c['part'], 'q': c['q'], 'sub': c['sub'],
                                     'law': law, 'article': n['article'], 'para': n.get('para', ''), 'basis': 'Claude 판단(검토 추가)',
                                     'confidence': c['confidence'], 'issue': c.get('issue', c.get('why', '')), 'kind': kind})
                        continue
                    hit = [r for r in rows if rkey(r) == rkey(c)]
                    if len(hit) != 1:
                        raise SystemExit(f'{folder}/corrections.jsonl: 고칠 줄을 하나로 찾지 못함 {rkey(c)} ({len(hit)}줄)')
                    if c['action'] == 'drop':
                        rows.remove(hit[0])
                    elif c['action'] == 'replace':
                        r = hit[0]
                        r.pop('current', None)
                        r['law'], r['article'], r['para'] = c['new']['law'], c['new']['article'], c['new'].get('para', '')
                        r['confidence'] = c['confidence']
        theory = set()
        if subq:
            for q in load(R / folder / subq):
                if q.get('qtype') == '이론':
                    theory.add((q['year'], q['part'], str(q['q']), str(q['sub'])))
        for r in rows:
            if r['basis'] == '문제지 발췌':
                continue
            if (r['year'], r['part'], str(r['q']), str(r['sub'])) in theory:
                continue
            exam = exam_of(r['part'])
            num = now_number(r)
            h = {'exam': exam, 'year': r['year'], 'round': r.get('round'), 'part': r['part'], 'q': str(r['q']),
                 'sub': str(r['sub']), 'issue': r.get('issue', ''), 'basis': r['basis'], 'confidence': r['confidence'],
                 'asked': {'law': r['law'], 'article': str(r.get('article') or ''), 'para': str(r.get('para') or '')},
                 'source': folder}
            if num is None:
                retired.append(h)
                continue
            h['law'], h['article'], h['para'], note = num
            if note:
                h['number_note'] = note
            hits.append(h)

    # 쓴 세트가 있으면 그 문(시험·연도·과목·문)은 세트의 근거 조문이 원장 매핑을 대신한다.
    # 세트를 쓰며 사례를 다시 읽고 고친 번호·더한 조문이 원장에 그대로 들어간다(26.11.07 영신 "원장에 다 넣고 계속 쓰자").
    written = {}
    for f in sorted((ROOT / 'data' / 'sets').glob('*.json')):
        st = json.loads(f.read_text(encoding='utf-8'))
        written[(st['exam'], st['year'], st['part'], st['q'])] = st
    hits = [h for h in hits if (h['exam'], h['year'], h['part'], h['q']) not in written]
    for (exam, year, part, q), st in written.items():
        for iss in st['issues']:
            for c in iss['cites']:
                hits.append({'exam': exam, 'year': year, 'round': st.get('round'), 'part': part, 'q': q, 'sub': str(iss.get('sub', '')),
                             'issue': st['title'], 'basis': '세트(Claude 판단)', 'confidence': c.get('confidence', '확인 필요'),
                             'asked': {'law': c['law'], 'article': str(c['jo']), 'para': str(c.get('para') or '')},
                             'source': 'data/sets/' + st['id'] + '.json',
                             'law': c['law'], 'article': str(c['jo']), 'para': str(c.get('para') or '')})

    # 나중 층(PRINCIPLES 1-2): 세트의 later와 카드 해설 속 '판례 법리' 메모를 모은다. 빈출도에는 세지 않는다.
    later = []
    for (exam, year, part, q), st in written.items():
        for x in st.get('later', []):
            later.append({'layer': x['layer'], 'set': st['id'], 'year': year, 'sub': x.get('sub', ''), 'issue': x['issue'],
                          'precedent': x.get('precedent', []), 'checked': x.get('checked', '')})
        for iss in st['issues']:
            for c in iss['cites']:
                for n in c.get('note', []):
                    if '판례 법리' in n:
                        later.append({'layer': '판례', 'set': st['id'], 'year': year, 'sub': str(iss.get('sub', '')), 'card': iss['id'],
                                      'law': c['law'], 'article': str(c['jo']), 'issue': n, 'precedent': [], 'checked': '판례 확인 전(카드 해설 메모)'})

    by = defaultdict(list)
    for h in hits:
        by[(h['law'], h['article'])].append(h)
    arts, archive = [], []
    for (law, art), hs in by.items():
        inwin = [h for h in hs if WINDOW[0] <= h['year'] <= WINDOW[1]]
        freq = {e: len({h['year'] for h in inwin if h['exam'] == e}) for e in exams}
        freq = {e: n for e, n in freq.items() if n}
        a = {
            'law': law, 'article': art,
            'paras': sorted({h['para'] for h in hs if h['para']}, key=lambda x: int(x) if x.isdigit() else 99),
            'freq': freq, 'freq_text': ' '.join(f'{e}{n}' for e, n in freq.items()),
            'years': sorted({h['year'] for h in inwin}),
            'last_year': max(h['year'] for h in hs),
            'needs_check': any(h['confidence'] != '확실' or h.get('number_note') for h in inwin or hs),
            'hits': sorted(inwin or hs, key=lambda h: (-h['year'], h['exam'], h['part'], h['q'], h['sub'])),
        }
        (arts if inwin else archive).append(a)
    order = lambda a: (-sum(a['freq'].values()), -a['last_year'], a['law'], int(''.join(c for c in a['article'] if c.isdigit()) or 0))
    arts.sort(key=order)
    archive.sort(key=lambda a: (-a['last_year'], a['law']))
    out = ROOT / 'data' / 'ledger'
    out.mkdir(parents=True, exist_ok=True)
    doc = {
        'version': ver,
        'window': list(WINDOW),
        'status': ('아홉 시험(v0 + 법무사·법원행정고시·5급 공채·입법고시·노무사·변리사·감정평가사 2017~2026). 매핑은 Claude, 영신 검수 전.'
                   if v1 else '변호사시험·사법시험만. 매핑은 Claude, 영신 검수 전. v1에서 노무사·변리사·감정평가사·법무사·5급·입법고시·법원행정고시를 더한다.'),
        'rules': '발췌 조문 제외, 현행 번호, 사례 설문만, 창 안 1회 이상이면 외울 조문, 빈출도는 시험별 회차 수.',
        'exams': exams,
        'counts': {'articles': len(arts), 'archive': len(archive), 'retired_rows': len(retired),
                   'later_판례': sum(1 for x in later if x['layer'] == '판례'), 'later_학설': sum(1 for x in later if x['layer'] == '학설')},
        'articles': arts, 'archive': archive, 'retired': retired,
        'later': sorted(later, key=lambda x: (x['layer'], -x['year'], x['set'])),
    }
    (out / f'ledger-{ver}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    # 세트: 기출 한 문. 사례 하나(민사의 '제1문의2'처럼 쪼개진 것도 하나)가 한 세트.
    sets = defaultdict(list)
    for h in hits:
        if WINDOW[0] <= h['year'] <= WINDOW[1]:
            sets[(h['exam'], h['year'], h['part'], h['q'])].append(h)
    plan = []
    for (exam, year, part, q), hs in sorted(sets.items(), key=lambda kv: (-kv[0][1], kv[0][0], kv[0][2], kv[0][3])):
        cards, seen = [], set()
        for h in sorted(hs, key=lambda h: (h['sub'], h['law'], h['article'])):
            k = (h['sub'], h['law'], h['article'], h['para'])
            if k in seen:
                continue
            seen.add(k)
            cards.append({'sub': h['sub'], 'law': h['law'], 'article': h['article'], 'para': h['para'],
                          'issue': h['issue'], 'confidence': h['confidence']})
        st = written.get((exam, year, part, q))
        if st:
            done = {c['stage'] for c in st.get('checks', []) if c['result'] in ('통과', '고침')}
            left = [x for x in STAGES if x not in done]
            status = '카드 씀 · ' + ('조문 층 검수 끝' if not left else '남은 검수: ' + ', '.join(left))
        else:
            status = '카드 쓰기 전'
        plan.append({'id': f'{exam}{year}-{part}-{q}', 'exam': exam, 'year': year, 'round': hs[0]['round'], 'part': part,
                     'q': q, 'cards': cards, 'status': status})
    (out / f'sets-{ver}.json').write_text(json.dumps({'version': ver, 'order': '최근 회차부터, 같은 해는 시험·과목·문 순',
                                                  'sets': plan}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f"외울 조문 {len(arts)} · 보관함 {len(archive)} · 원장 밖 {len(retired)}줄 · 세트 {len(plan)} · 카드 {sum(len(s['cards']) for s in plan)}"
          f" · 나중 층 판례 {doc['counts']['later_판례']} 학설 {doc['counts']['later_학설']}")


if __name__ == '__main__':
    main()
