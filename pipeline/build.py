#!/usr/bin/env python3
"""법학고양 시제품을 조립한다: data/ + sources/ + pipeline/game.html → proto.html(생성물).

사용: python3 -I pipeline/build.py [--artifact <파일>]
- proto.html: 혼자 열리는 완성 문서(나중에 GitHub Pages용).
- --artifact: claude.ai Artifact 미리보기용(문서 껍데기 없이 본문만).
생성물(proto.html)을 손으로 고치지 않는다. game.html·judge.js·data/를 고치고 다시 조립한다.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'pipeline'


def part_text(text, part):
    """본문·단서를 원문 경계에서 자른다(설계안 B3). 민법의 옛 단서는 '그러나', 요즘 단서는 '다만,'으로 시작한다."""
    if not part:
        return text
    m = re.search(r'\s(그러나|다만,)\s', text)
    if not m:
        raise SystemExit(f'본문·단서 경계를 못 찾음: {text[:40]}')
    if part == '본문':
        return text[:m.start()].strip()
    if part == '단서':
        return text[m.start():].strip()
    raise SystemExit(f'모르는 부분: {part}')


def main():
    deck = json.loads((ROOT / 'data' / 'proto-cards.json').read_text(encoding='utf-8'))
    src = json.loads((ROOT / deck['source']).read_text(encoding='utf-8'))
    near = json.loads((ROOT / 'data' / 'near.json').read_text(encoding='utf-8'))['pairs']
    header = src['header']
    when = re.sub(r'\]\s*\[', '] [', header or '')

    def cite_of(ci):
        art = src['articles'][ci['jo']]
        paras = art['paras']
        if ci.get('para'):
            text = paras[ci['para'] - 1]['text']
        else:
            if len(paras) != 1:
                raise SystemExit(f"제{ci['jo']}조는 항이 여럿이라 para를 정해야 함")
            text = paras[0]['text']
        text = part_text(text, ci.get('part'))
        if ci.get('phrase') and not re.sub(r'\s+', ' ', text).startswith(ci['phrase']):
            raise SystemExit(f"제{ci['jo']}조 첫 문구가 원문 앞부분과 다름: {ci['phrase']}")
        tail = (f" 제{ci['para']}항" if ci.get('para') else '') + (f" {ci['part']}" if ci.get('part') else '')
        return {
            'law': ci['law'], 'jo': ci['jo'], 'title': art['title'], 'text': text,
            'cite': f"{ci['jo']}조{tail}",
            'label': f"{ci['law']} 제{ci['jo']}조{tail}",
            'joLabel': f"제{ci['jo']}조",
            'skey': ':'.join(str(x) for x in [ci['law'], ci['jo'], ci.get('para'), ci.get('part')] if x),
            'phrase': ci.get('phrase', ''), 'note': ci.get('note', []),
        }

    cards = []
    for case in deck['cases']:
        for iss in case['issues']:
            done = []
            for k, ci in enumerate(iss['cites']):
                c = cite_of(ci)
                prefix = iss['answer'] + '(' + ci['law'] + ' 제'
                for d in done:
                    prefix += d['cite'] + ' ' + d['text'] + ' 제'
                c.update({
                    'id': iss['id'] + ('abcdefgh'[k] if len(iss['cites']) > 1 else ''),
                    'caseId': case['id'], 'caseLabel': case['label'], 'facts': case['facts'],
                    'q': iss['q'], 'answer': '', 'prefix': prefix, 'suffix': ')',
                    'srcLine': f"{c['law']} 제{c['jo']}조({c['title']}) · {when} · law.go.kr 웹 화면 두 곳 대조(API 키 전 임시, {src['fetched']})",
                })
                cards.append(c)
                done.append(c)
    articles = [{'label': f'제{jo}조', 'text': ' '.join(p['text'] for p in a['paras'])} for jo, a in src['articles'].items()]
    data = {
        'id': deck['id'], 'runKey': deck['cases'][0]['id'], 'title': deck['title'], 'label': deck['cases'][0]['label'],
        'foot': f"조문: law.go.kr {src['law']} {when}. API 키를 받기 전이라 웹 화면 두 곳을 대조해 받은 임시본이다. 사례·답안·해설은 Claude가 쓴 임시 예시이고 기출이 아니다.",
        'cards': cards, 'articles': articles, 'near': near,
    }
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
    cut = page.index('</style>') + len('</style>')
    head, body = page[:cut], page[cut:]
    full = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<!-- 생성물: python3 -I pipeline/build.py 로 만든다. 고치지 말 것. -->\n'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}</style>\n'
            + head + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n')
    (ROOT / 'proto.html').write_text(full, encoding='utf-8')
    print('proto.html', len(cards), '장')
    if '--artifact' in sys.argv:
        # Artifact 미리보기는 파일 내려받기가 막혀 기록 옮기기가 동작하지 않는다. 그래서 그 단추와 코드를 뺀다.
        prev = re.sub(r'<!-- RECORD_TRANSFER_UI_START -->.*?<!-- RECORD_TRANSFER_UI_END -->', '', page, flags=re.S)
        prev = re.sub(r'<script id="record-transfer">.*?</script>', '', prev, flags=re.S)
        out = Path(sys.argv[sys.argv.index('--artifact') + 1])
        out.write_text(prev, encoding='utf-8')
        print(out)


if __name__ == '__main__':
    main()
