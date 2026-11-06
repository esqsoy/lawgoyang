#!/usr/bin/env python3
"""law.go.kr 웹 화면에서 조문을 받아 두 화면을 글자 단위로 대조한다(Open API 키 전 임시).

사용:
  python3 -I pipeline/fetch_web.py --law 민법 --lsi 284415 --ef 20260317 \
      --jo 750 756 763 396 --cache <내려받을 빈 폴더> --out sources/web/minbeop-20260317.json
  python3 -I pipeline/fetch_web.py --ledger data/ledger/ledger-v0.json --cache <빈 폴더> --outdir sources/web/laws
    (원장의 외울 조문을 법령별로 다 받는다. 법령 이름으로 현행 lsiSeq·시행일을 찾는다. 결과 목록은 outdir/index.json)

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
NOTE = re.compile(r'\s*(?:<(?:개정|신설|전문개정|본조신설|제목개정|타법개정)[^>]*>|\[(?:개정|신설|전문개정|본조신설|제목개정|타법개정|시행일|종전|제\d+조)[^\]]*\])\s*')


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


def split_jo(jo):
    """'82의4' → (82, 4), '750' → (750, 0)"""
    m = re.fullmatch(r'(\d+)(?:의(\d+))?', str(jo))
    if not m:
        raise SystemExit(f'조 번호 꼴이 이상함: {jo}')
    return int(m.group(1)), int(m.group(2) or 0)


def shape(lines, jo):
    """[p 글] → {title, paras:[{no, text}], notes}"""
    main, br = split_jo(jo)
    head = re.match(r'^제%d조%s(?:\(([^)]*)\))?\s*' % (main, f'의{br}' if br else ''), lines[0])
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
        if re.fullmatch(r'\[[^\]]*\]', t):
            # 위헌·헌법불합치 결정 같은 대괄호 표시만 있는 줄: 조문 글이 아니라 표시다. 버리지 않고 notes에 둔다.
            notes.append(t)
            continue
        ho = re.match(r'^(\d+)(?:의(\d+))?\.\s*(.*)$', t)
        mok = re.match(r'^([가-하])\.\s*(.*)$', t)
        if ho and paras:
            # 호: 바로 앞 항 아래에 둔다(제111조 제1항 제4호처럼 인용한다)
            paras[-1].setdefault('ho', []).append({'no': ho.group(1) + (f'의{ho.group(2)}' if ho.group(2) else ''), 'text': ho.group(3).strip()})
            continue
        if mok and paras and paras[-1].get('ho'):
            paras[-1]['ho'][-1].setdefault('mok', []).append({'no': mok.group(1), 'text': mok.group(2).strip()})
            continue
        no = None
        if t[0] in CIRCLED:
            no, t = CIRCLED.index(t[0]) + 1, t[1:].strip()
        paras.append({'no': no, 'text': t})
    return {'title': title, 'paras': paras, 'notes': notes}


def fetch_law(law, lsi, ef, jos, cache):
    """한 법령의 조문들을 두 화면에서 받아 대조한다. 반환: 문서 dict"""
    cache.mkdir(parents=True, exist_ok=True)
    full = get(f'{BASE}lsInfoR.do?lsiSeq={lsi}&efYd={ef}', cache / f'full-{lsi}-{ef}.html')
    header = re.search(r'\[시행 [^\]]*\]\s*\[[^\]]*\]', full)
    whole = parse(full)
    arts = {}
    for jo in jos:
        main, br = split_jo(jo)
        side = get(f'{BASE}lsSideInfoP.do?lsiSeq={lsi}&joNo={main:04d}&joBrNo={br:02d}&docCls=jo&urlMode=lsScJoRltInfoR',
                   cache / f'side-{lsi}-{main:04d}-{br:02d}.html')
        one = parse(side).get(f'{main}:{br}')
        two = whole.get(f'{main}:{br}')
        if not one or not two:
            raise SystemExit(f'{law} 제{jo}조를 한쪽 화면에서 못 찾음(조문 하나: {bool(one)}, 전체: {bool(two)})')
        if one != two:
            raise SystemExit(f'{law} 제{jo}조 두 화면이 다름\n 조문 하나: {one}\n 전체: {two}')
        arts[str(jo)] = shape(two, jo)
        time.sleep(0.6)
    return {
        'law': law, 'lsiSeq': lsi, 'efYd': ef,
        'header': header.group(0) if header else None,
        'fetched': datetime.date.today().isoformat(),
        'method': 'law.go.kr 웹 화면 두 곳(lsInfoR 전체·lsSideInfoP 조문 하나)을 따로 받아 글자 단위로 대조. Open API 키 전 임시.',
        'source': f'{BASE}lsInfoR.do?lsiSeq={lsi}&efYd={ef}',
        'articles': arts,
    }


OFFICIAL = {'헌법': '대한민국헌법'}


def find_current(name, cache):
    """법령 이름 → 현행 (lsiSeq, efYd). law.go.kr/법령/이름 화면의 틀(iframe) 주소에서 읽는다."""
    from urllib.parse import quote
    page = get('https://www.law.go.kr/' + quote('법령') + '/' + quote(name), cache / f'name-{abs(hash(name)) % 10**8}.html')
    m = re.search(r'lsInfoP\.do\?lsiSeq=(\d+)[^"\']*?efYd=(\d+)', page)
    if not m:
        raise SystemExit(f'현행 법령을 못 찾음: {name}')
    return m.group(1), m.group(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--law')
    ap.add_argument('--lsi')
    ap.add_argument('--ef')
    ap.add_argument('--jo', nargs='+')
    ap.add_argument('--cache', required=True)
    ap.add_argument('--out')
    ap.add_argument('--ledger')
    ap.add_argument('--outdir')
    a = ap.parse_args()
    cache = Path(a.cache)
    if a.ledger:
        led = json.loads(Path(a.ledger).read_text(encoding='utf-8'))
        want = {}
        for art in led['articles']:
            want.setdefault(art['law'], set()).add(art['article'])
        outdir = Path(a.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        index = {}
        missing = {}
        for law in sorted(want):
            name = OFFICIAL.get(law, law)
            try:
                lsi, ef = find_current(name, cache)
            except SystemExit as err:
                # 이름이 바뀌었거나 없어진 법령: 멈추지 않고 목록에 남긴다(원장 확인 필요)
                missing[law] = {'official': name, 'articles': sorted(want[law]), 'why': str(err)}
                print(law, '못 찾음')
                continue
            jos = sorted(want[law], key=lambda j: split_jo(j))
            doc = fetch_law(name, lsi, ef, jos, cache / lsi)
            f = outdir / f'{lsi}-{ef}.json'
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            index[law] = {'official': name, 'lsiSeq': lsi, 'efYd': ef, 'header': doc['header'], 'file': f.name, 'articles': len(jos)}
            print(law, lsi, ef, len(jos), '조 두 화면 일치')
        if missing:
            index['_missing'] = missing
        (outdir / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return
    doc = fetch_law(a.law, a.lsi, a.ef, a.jo, cache)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(out, '조문', len(doc['articles']), '두 화면 일치')


if __name__ == '__main__':
    main()
