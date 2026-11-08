#!/usr/bin/env python3
"""법학고양 시제품을 조립한다: data/ + sources/ + pipeline/game.html → proto.html(생성물).

사용: python3 -I pipeline/build.py [--artifact <파일>] [--check] [--only 세트id,세트id]
- --check: 조립·검사만 하고 파일은 쓰지 않는다. --only: 그 세트만 읽는다(임시판은 늘 포함).
- proto.html: 혼자 열리는 완성 문서(나중에 GitHub Pages용).
- --artifact: claude.ai Artifact 미리보기용(문서 껍데기 없이 본문만).
생성물(proto.html)을 손으로 고치지 않는다. game.html·judge.js·data/를 고치고 다시 조립한다.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'pipeline'


def part_text(text, part):
    """본문·단서, 전문·후문을 원문 경계에서 자른다(설계안 B3).
    단서는 '그러나'(민법 등 옛 법)·'다만,'으로 시작한다. 전문·후문은 첫 마침표 뒤에서 나눈다(단서가 아닌 둘째 문장)."""
    if not part:
        return text
    if part in ('전문', '후문'):
        # 괄호 밖의 첫 마침표에서 나눈다('(…포함한다. 이하 같다)'의 마침표는 경계가 아니다)
        depth, cut = 0, None
        for k, ch in enumerate(text):
            if ch in '(（':
                depth += 1
            elif ch in ')）':
                depth = max(0, depth - 1)
            elif ch == '.' and depth == 0 and k + 1 < len(text) and text[k + 1].isspace():
                cut = k
                break
        if cut is None:
            raise SystemExit(f'전문·후문 경계를 못 찾음: {text[:40]}')
        return text[:cut + 1].strip() if part == '전문' else text[cut + 1:].strip()
    m = re.search(r'\s(그러나|다만,)\s', text)
    if not m:
        raise SystemExit(f'본문·단서 경계를 못 찾음: {text[:40]}')
    if part == '본문':
        return text[:m.start()].strip()
    if part == '단서':
        return text[m.start():].strip()
    raise SystemExit(f'모르는 부분: {part}')


TRACKS = ['공법', '민사', '연습']


def prec_line(x):
    """판례연구로 확인한 판결 한 줄(PRINCIPLES 1-2)."""
    return f"판례: {x['court']} {x['date']} 선고 {x['no']} {x.get('kind', '판결')} — {x['point']} ({x['checked']})"


def law_notes(art):
    """조문에 붙은 표시 가운데 카드에 보일 것: 위헌·헌법불합치 결정(첫 하나), 2025년 이후 개정(날짜를 모아 한 줄).
    표시는 조 단위라 인용한 항과 다른 항에 관한 것일 수 있다. PRINCIPLES 2 '개정되면 바뀐 조문을 표시'."""
    out, dates = [], []
    for n in art.get('notes', []):
        if re.search(r'위헌|헌법불합치', n):
            if not any('결정(조문에 붙은 표시)' in o for o in out):
                out.append('결정(조문에 붙은 표시): ' + n.strip('[]<> '))
            continue
        m = re.search(r'(전문개정|개정|신설)\s*(20\d\d\.\s*\d+\.\s*\d+\.)', n)
        if m and int(m.group(2)[:4]) >= 2025 and m.group(2) not in dates:
            dates.append(m.group(2))
    if dates:
        out.append('최근 개정: 이 조는 ' + ', '.join(dates) + ' 개정됐다(인용한 항이 아닐 수 있다).')
    return out


def pick_para(art, para, jo):
    paras = art['paras']
    if para:
        for i, p in enumerate(paras):
            if p['no'] == para or (p['no'] is None and i == para - 1):
                return p
        raise SystemExit(f'제{jo}조 제{para}항이 없음')
    if len(paras) != 1:
        raise SystemExit(f'제{jo}조는 항이 여럿이라 para를 정해야 함')
    return paras[0]


def main():
    near = json.loads((ROOT / 'data' / 'near.json').read_text(encoding='utf-8'))['pairs']
    ledger = json.loads((ROOT / 'data' / 'ledger' / 'ledger-v0.json').read_text(encoding='utf-8'))
    freq = {(a['law'], a['article']): a['freq_text'] for a in ledger['articles']}
    idx_path = ROOT / 'sources' / 'web' / 'laws' / 'index.json'
    index = json.loads(idx_path.read_text(encoding='utf-8')) if idx_path.exists() else {}
    srcs = {}

    def source(law, fallback=None):
        if law not in srcs:
            if law in index:
                srcs[law] = json.loads((idx_path.parent / index[law]['file']).read_text(encoding='utf-8'))
            elif fallback:
                srcs[law] = json.loads((ROOT / fallback).read_text(encoding='utf-8'))
            else:
                raise SystemExit(f'조문 원문이 없음: {law} (pipeline/fetch_web.py --ledger 로 받는다)')
        return srcs[law]

    def cite_of(ci, fallback=None):
        src = source(ci['law'], fallback)
        jo = str(ci['jo'])
        if jo not in src['articles'] and fallback:
            key = ci['law'] + '@' + fallback
            if key not in srcs:
                srcs[key] = json.loads((ROOT / fallback).read_text(encoding='utf-8'))
            src = srcs[key]
        if jo not in src['articles']:
            raise SystemExit(f"{ci['law']} 제{jo}조 원문이 없음")
        art = src['articles'][jo]
        p = pick_para(art, ci.get('para'), jo)
        if ci.get('lead'):
            # 호가 있는 항의 머리글만 외울 때(행정절차법 제21조 제1항 등)
            text = p['text']
        elif ci.get('ho'):
            hs = [h for h in p.get('ho', []) if h['no'] == str(ci['ho'])]
            if not hs:
                raise SystemExit(f"{ci['law']} 제{jo}조 제{ci.get('para')}항 제{ci['ho']}호가 없음")
            text = hs[0]['text']
        else:
            if p.get('ho'):
                raise SystemExit(f"{ci['law']} 제{jo}조 제{ci.get('para') or ''}항은 호가 있어 ho를 정해야 함")
            text = p['text']
        text = part_text(text, ci.get('part'))
        if ci.get('phrase') and not re.sub(r'\s+', ' ', text).startswith(ci['phrase']):
            raise SystemExit(f"{ci['law']} 제{jo}조 첫 문구가 원문 앞부분과 다름: {ci['phrase']}")
        tail = (f" 제{ci['para']}항" if ci.get('para') else '') + (f" 제{ci['ho']}호" if ci.get('ho') else '') + (f" {ci['part']}" if ci.get('part') else '')
        when = re.sub(r'\]\s*\[', '] [', src.get('header') or '')
        return {
            'law': ci['law'], 'jo': jo, 'title': art['title'], 'text': text,
            'cite': f"{jo}조{tail}", 'label': f"{ci['law']} 제{jo}조{tail}", 'joLabel': f"제{jo}조",
            'skey': ':'.join(str(x) for x in [ci['law'], jo, ci.get('para'), ci.get('ho'), ci.get('part')] if x),
            'phrase': ci.get('phrase', ''), 'note': ci.get('note', []) + [prec_line(x) for x in ci.get('precedent', [])] + law_notes(art),
            'conf': ci.get('confidence', ''), 'research': ci.get('research', ''),
            'freq': freq.get((ci['law'], jo), ''),
            'srcLine': f"{ci['law']} 제{jo}조" + (f"({art['title']})" if art['title'] else '') + f" · {when} · law.go.kr 웹 화면 두 곳 대조(API 키 전 임시, {src['fetched']})",
        }

    pending = []

    def cards_of(set_id, label, facts, issues, exam_src, fallback=None):
        out = []
        for iss in issues:
            if any(ci.get('pending') for ci in iss['cites']):
                # 원문을 아직 받지 않은 조문(세트 쓰는 중 더한 것): 원장에는 들어가고, 카드는 원문을 받은 뒤 만든다
                pending.append(iss['id'])
                continue
            done = []
            for k, ci in enumerate(iss['cites']):
                c = cite_of(ci, fallback)
                prefix = iss['answer'] + '(' + ci['law'] + ' 제'
                for d in done:
                    prefix += d['cite'] + ' ' + d['text'] + ' 제'
                last = k == len(iss['cites']) - 1
                c.update({'id': iss['id'] + ('abcdefgh'[k] if len(iss['cites']) > 1 else ''), 'setId': set_id,
                          'caseId': set_id, 'caseLabel': label, 'facts': facts, 'q': iss['q'], 'answer': '',
                          'prefix': prefix, 'suffix': ')' + (iss.get('after', '') if last else ''), 'examSrc': exam_src})
                out.append(c)
                done.append(c)
        return out

    sets = []
    deck = json.loads((ROOT / 'data' / 'proto-cards.json').read_text(encoding='utf-8'))
    case = deck['cases'][0]
    sets.append({'id': 'proto', 'track': '연습', 'title': '임시 사례 · 배달 자전거 사고', 'label': '민법 불법행위 · 기출 아님',
                 'status': '', 'cards': cards_of('proto', case['label'], case['facts'], case['issues'], '', deck['source'])})
    only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
    for f in sorted((ROOT / 'data' / 'sets').glob('*.json')):
        st = json.loads(f.read_text(encoding='utf-8'))
        if only and st['id'] not in only:
            continue
        src = st['source']
        exam_src = f"출처: {src['org']}, {src['name']}({st['year']}), 공공누리 {src['kogl']}, {src['url']}"
        label = f"{src['short']}"
        sets.append({'id': st['id'], 'track': st['track'], 'title': st['title'], 'label': label, 'year': st['year'],
                     'q': st['q'], 'status': st.get('status_short', ''), 'later': st.get('later', []),
                     'cards': cards_of(st['id'], label, st['facts'], st['issues'], exam_src)})
    sets.sort(key=lambda x: (TRACKS.index(x['track']), -x.get('year', 0), x.get('q', '')))
    articles = {}
    for key, src in srcs.items():
        law = key.split('@')[0]
        articles.setdefault(law, [])
        have = {a['label'] for a in articles[law]}
        articles[law] += [a for a in [{'label': f'제{jo}조', 'text': ' '.join(p['text'] + ' ' + ' '.join(h['text'] for h in p.get('ho', [])) for p in a['paras'])}
                         for jo, a in src['articles'].items()] if a['label'] not in have]
    data = {
        'tracks': TRACKS, 'sets': sets, 'articles': articles, 'near': near,
        'foot': '조문: law.go.kr 현행 법령. API 키를 받기 전이라 웹 화면 두 곳을 대조해 받은 임시본이다. 기출 사례는 세트마다 출처(공공누리)를 단다. 답안·해설은 Claude가 쓴 초안이고 영신 검수 전이다. 법학고양은 출제 기관과 관계없는 학습 게임이다.',
    }
    cards = [c for st in sets for c in st['cards']]
    rt = {'game': '법학고양', 'app': 'lawgoyang-records', 'prefix': 'lawgoyang-', 'skip': [], 'target': 'proto.html',
          'kinds': {'progress': '^lawgoyang-progress-v1$', 'missed': '^lawgoyang-(stage|missed)-v1$'}}

    def js_json(o):
        return json.dumps(o, ensure_ascii=False).replace('</', '<\\/')

    page = (P / 'game.html').read_text(encoding='utf-8')
    page = page.replace('@JUDGE@', (P / 'judge.js').read_text(encoding='utf-8'))
    page = page.replace('@DATA@', js_json(data))
    page = page.replace('@RT_CONFIG@', js_json(rt))
    page = page.replace('@RT_CODE@', (P / 'record-transfer.js').read_text(encoding='utf-8'))
    left = re.findall(r'@[A-Z_]+@', page)
    if left:
        raise SystemExit(f'채우지 못한 자리: {left}')
    if pending:
        print('원문 받기 전이라 건너뛴 카드', len(pending), ':', ', '.join(pending))
    if '--check' in sys.argv:
        # 검사만: 결과 파일을 쓰지 않는다(여럿이 동시에 돌려도 부딪히지 않게)
        for st in sets:
            print(st['id'], len(st['cards']), '장 확인')
        return
    cut = page.index('</style>') + len('</style>')
    head, body = page[:cut], page[cut:]
    full = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<!-- 생성물: python3 -I pipeline/build.py 로 만든다. 고치지 말 것. -->\n'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}</style>\n'
            + head + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n')
    (ROOT / 'proto.html').write_text(full, encoding='utf-8')
    print('proto.html', len(sets), '세트', len(cards), '장')
    if '--artifact' in sys.argv:
        # Artifact 미리보기는 파일 내려받기가 막혀 기록 옮기기가 동작하지 않는다. 그래서 그 단추와 코드를 뺀다.
        prev = re.sub(r'<!-- RECORD_TRANSFER_UI_START -->.*?<!-- RECORD_TRANSFER_UI_END -->', '', page, flags=re.S)
        prev = re.sub(r'<script id="record-transfer">.*?</script>', '', prev, flags=re.S)
        out = Path(sys.argv[sys.argv.index('--artifact') + 1])
        out.write_text(prev, encoding='utf-8')
        print(out)


if __name__ == '__main__':
    main()
