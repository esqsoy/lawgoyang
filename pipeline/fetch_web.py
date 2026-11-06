#!/usr/bin/env python3
"""law.go.kr 웹 화면에서 조문을 받아 두 화면을 글자 단위로 대조한다(Open API 키 전 임시).

사용:
  python3 -I pipeline/fetch_web.py --law 민법 --lsi 284415 --ef 20260317 \
      --jo 750 756 763 396 --cache <내려받을 빈 폴더> --out sources/web/minbeop-20260317.json

- 전체 법령 화면(LSW/lsInfoR.do)과 조문 하나 화면(LSW/lsSideInfoP.do)을 따로 받아,
  각각 HTML 파서로 조문 글을 뽑고 둘이 한 글자라도 다르면 멈춘다.
- 태그를 지우며 줄을 바꾸면 조문 속 링크 말(헌법 제37조 제1항의 '헌법')이 떨어져 나간다(PRINCIPLES 2 사례).
  그래서 <p> 단위로 글을 모으고, 그 안의 <a>·<span> 글은 이어 붙인다.
- '<개정 2014. 12. 30.>' 같은 개정 표시는 조문 글에서 떼어 notes에 둔다.
- API 키가 오면 이 파일 대신 API로 받고, 여기서 받은 글과 대조한다(HANDOFF).
"""
import argparse, datetime, html, json, re, time, urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://www.law.go.kr/LSW/'
CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
NOTE = re.compile(r'\s*<(개정|신설|전문개정|본조신설|제목개정)[^>]*>\s*')


def get(url, path, tries=4):
    if path.exists() and path.stat().st_size > 1000:
        return path.read_text(encoding='utf-8')
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'lawgoyang-fetch'})
            data = urllib.request.urlopen(req, timeout=40).read().decode('utf-8')
            path.write_text(data, encoding='utf-8')
            return data
        except Exception as err:  # 연결이 끊기면 조금 쉬고 다시
            if k == tries - 1:
                raise
            time.sleep(2 ** (k + 1))


class LawP(HTMLParser):
    """div.lawcon 안의 <p> 글을 순서대로 모은다. a name="J{조}:{가지}"로 어느 조문인지 안다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cur = None      # 지금 조문 열쇠 '750:0'
        self.depth = 0       # div.lawcon 깊이
        self.inp = False
        self.buf = []
        self.out = {}        # 열쇠 → [p 글]
        self.skip = 0        # <script>/<style> 안

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'a' and a.get('name', '').startswith('J') and ':' in a.get('name', ''):
            self.cur = a['name'][1:]
        if tag == 'div':
            if self.depth:
                self.depth += 1
            elif 'lawcon' in (a.get('class') or '').split():
                self.depth = 1
        if tag == 'p' and self.depth:
            self.inp, self.buf = True, []
        if tag == 'br' and self.inp:
            self.buf.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
        if tag == 'p' and self.inp:
            text = re.sub(r'[ \t\r\n\xa0]+', ' ', ''.join(self.buf)).strip()
            if text and self.cur:
                self.out.setdefault(self.cur, []).append(text)
            self.inp = False
        if tag == 'div' and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.inp and not self.skip:
            self.buf.append(data)


def parse(page):
    p = LawP()
    p.feed(page)
    return p.out


def shape(lines, jo):
    """[p 글] → {title, paras:[{no, text}], notes}"""
    head = re.match(r'^제%s조(?:의\d+)?(?:\(([^)]*)\))?\s*' % jo, lines[0])
    if not head:
        raise SystemExit(f'제{jo}조 머리를 못 찾음: {lines[0][:40]}')
    title = head.group(1)
    body = [lines[0][head.end():]] + lines[1:]
    paras, notes = [], []
    for t in body:
        for m in NOTE.finditer(t):
            notes.append(m.group(0).strip())
        t = NOTE.sub(' ', t).strip()
        if not t:
            continue
        no = None
        if t[0] in CIRCLED:
            no, t = CIRCLED.index(t[0]) + 1, t[1:].strip()
        paras.append({'no': no, 'text': t})
    return {'title': title, 'paras': paras, 'notes': notes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--law', required=True)
    ap.add_argument('--lsi', required=True)
    ap.add_argument('--ef', required=True)
    ap.add_argument('--jo', nargs='+', required=True)
    ap.add_argument('--cache', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    full = get(f'{BASE}lsInfoR.do?lsiSeq={a.lsi}&efYd={a.ef}', cache / f'full-{a.lsi}-{a.ef}.html')
    header = re.search(r'\[시행 [^\]]*\]\s*\[[^\]]*\]', full)
    whole = parse(full)
    arts = {}
    for jo in a.jo:
        side = get(f'{BASE}lsSideInfoP.do?lsiSeq={a.lsi}&joNo={int(jo):04d}&joBrNo=00&docCls=jo&urlMode=lsScJoRltInfoR',
                   cache / f'side-{a.lsi}-{int(jo):04d}.html')
        one = parse(side).get(f'{jo}:0')
        two = whole.get(f'{jo}:0')
        if not one or not two:
            raise SystemExit(f'제{jo}조를 한쪽 화면에서 못 찾음(조문 하나: {bool(one)}, 전체: {bool(two)})')
        if one != two:
            raise SystemExit(f'제{jo}조 두 화면이 다름\n 조문 하나: {one}\n 전체: {two}')
        arts[jo] = shape(two, jo)
        time.sleep(1)
    doc = {
        'law': a.law,
        'lsiSeq': a.lsi,
        'efYd': a.ef,
        'header': header.group(0) if header else None,
        'fetched': datetime.date.today().isoformat(),
        'method': 'law.go.kr 웹 화면 두 곳(lsInfoR 전체·lsSideInfoP 조문 하나)을 따로 받아 글자 단위로 대조. Open API 키 전 임시.',
        'source': f'{BASE}lsInfoR.do?lsiSeq={a.lsi}&efYd={a.ef}',
        'articles': arts,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(out, '조문', len(arts), '두 화면 일치')


if __name__ == '__main__':
    main()
