#!/usr/bin/env python3
"""기출 조문 원장 v0을 조립한다: research/의 매핑 네 개 → data/ledger/ledger-v0.json, sets-v0.json.

사용: python3 -I pipeline/ledger.py
- v0은 변호사시험(공법·민사 사례형 2012~2026)과 사법시험 2차(공법 2002~2017, 민사 2003~2017)만 담는다.
  매핑은 Claude가 했고 영신 검수 전이다. 노무사·변리사·감정평가사·법무사·5급·입법고시·법원행정고시는 v1에서 더한다.
- 규칙(PRINCIPLES 1, 설계안 A1·A4):
  · 문제지 발췌 조문(시험장에서 붙여 주는 개별법)은 넣지 않는다.
  · 현행 번호로 센다. 현행에 없는 조문('없음')과 현행 조문을 대지 못한 법리 행은 원장 밖(retired)에 둔다.
  · 창은 최근 10개 연도(지금 2017~2026). 창 안에 한 번이라도 나오면 외울 조문, 아니면 보관함.
  · 빈출도는 시험 한 글자 + 창 안에서 나온 해(회차) 수: 변8 사1.
  · 사시의 '이론' 설문(subq.jsonl qtype)은 사례형이 아니라서 뺀다.
- sets-v0.json: 세트 = 기출 한 문(시험·연도·과목·문), 최근 회차부터. 카드 = 그 문의 (설문, 조문) 하나.
- data/sets/에 쓴 세트가 있으면 그 문은 세트의 근거 조문으로 센다(원장 매핑을 대신한다).
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / 'research'
WINDOW = (2017, 2026)
EXAM = {'변': '변호사시험', '사': '사법시험'}
SOURCES = [
    ('gongbeop-pilot-20261107', None),
    ('minsa-pilot-20261107', None),
    ('sasi-gongbeop-20261107', 'subq.jsonl'),
    ('sasi-minsa-20261107', 'subq.jsonl'),
]


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


def main():
    hits, retired = [], []
    for folder, subq in SOURCES:
        rows = load(R / folder / 'mapping.jsonl')
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
            exam = '사' if r['part'].startswith('사시') else '변'
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

    by = defaultdict(list)
    for h in hits:
        by[(h['law'], h['article'])].append(h)
    arts, archive = [], []
    for (law, art), hs in by.items():
        inwin = [h for h in hs if WINDOW[0] <= h['year'] <= WINDOW[1]]
        freq = {e: len({h['year'] for h in inwin if h['exam'] == e}) for e in EXAM}
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
        'version': 'v0',
        'window': list(WINDOW),
        'status': '변호사시험·사법시험만. 매핑은 Claude, 영신 검수 전. v1에서 노무사·변리사·감정평가사·법무사·5급·입법고시·법원행정고시를 더한다.',
        'rules': '발췌 조문 제외, 현행 번호, 사례 설문만, 창 안 1회 이상이면 외울 조문, 빈출도는 시험별 회차 수.',
        'exams': EXAM,
        'counts': {'articles': len(arts), 'archive': len(archive), 'retired_rows': len(retired)},
        'articles': arts, 'archive': archive, 'retired': retired,
    }
    (out / 'ledger-v0.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

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
        plan.append({'id': f'{exam}{year}-{part}-{q}', 'exam': exam, 'year': year, 'round': hs[0]['round'], 'part': part,
                     'q': q, 'cards': cards, 'status': '카드 쓰기 전'})
    (out / 'sets-v0.json').write_text(json.dumps({'version': 'v0', 'order': '최근 회차부터, 같은 해는 시험·과목·문 순',
                                                  'sets': plan}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f"외울 조문 {len(arts)} · 보관함 {len(archive)} · 원장 밖 {len(retired)}줄 · 세트 {len(plan)} · 카드 {sum(len(s['cards']) for s in plan)}")


if __name__ == '__main__':
    main()
