#!/usr/bin/env python3
"""law.go.kr Open API(DRF)로 현행 조문을 받는다. fetch_web.py(웹 화면 임시본)와 같은 꼴로 쓴다.

사용:
  python3 -I pipeline/fetch_api.py --ledger data/ledger/ledger-v1.json --cache <저장소 밖 폴더> --outdir sources/api/laws
    원장 외울 조문을 법령별로 받는다. 법령 이름으로 현행 법령일련번호(MST)·시행일을 찾는다.
    법령 전체 응답(JSON)은 cache에 두고, outdir에는 원장 조문만 웹 임시본과 같은 꼴로 쓴다(index.json 포함).
  python3 -I pipeline/fetch_api.py --compare sources/web/laws --cache <같은 폴더>
    웹 임시본의 조문마다 API 글과 제목·항·호·목을 글자 단위로 대조한다(HANDOFF: 키가 오면 웹 임시본과 대조).

키(OC)는 저장소에 두지 않는다. 환경변수 LAW_OC 또는 ~/.config/lawgoyang/oc 에서 읽는다.
조문 꼴: {title, paras:[{no, text, ho:[{no, text, mok:[{no, text}]}]}], notes}. 항 번호는 숫자(①→1), 항이 없으면 no=None.
'<개정 2014. 12. 30.>', '[전문개정 …]' 같은 개정 표시는 글에서 떼어 notes에 둔다.
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

DRF = 'https://www.law.go.kr/DRF/'
CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
NOTE = re.compile(r'\s*(?:<(?:개정|신설|전문개정|본조신설|제목개정|타법개정)[^>]*>|\[(?:개정|신설|전문개정|본조신설|제목개정|타법개정|시행일|종전|제\d+조)[^\]]*\])\s*')
ALIAS = {'헌법': '대한민국헌법'}  # 원장 이름 → law.go.kr 정식 이름
HEAD = re.compile(r'^제(\d+)조(?:의(\d+))?(?:\(([^)]*)\))?\s*')


def oc():
    v = os.environ.get('LAW_OC')
    if v:
        return v.strip()
    p = Path.home() / '.config' / 'lawgoyang' / 'oc'
    if p.exists():
        return p.read_text(encoding='utf-8').strip()
    sys.exit('Open API 키가 없다: LAW_OC 환경변수나 ~/.config/lawgoyang/oc 에 넣는다.')


def call(path, params, tries=5):
    q = urllib.parse.urlencode({'OC': oc(), **params})
    for k in range(tries):
        try:
            req = urllib.request.Request(DRF + path + '?' + q, headers={'User-Agent': 'lawgoyang-fetch'})
            data = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
            return json.loads(data)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** (k + 1))


def find_current(name):
    """법령 이름 → 현행 {id, mst, ef, kind, pending}. 시행일 법령 목록(eflaw)에서 이름이 똑같고 '현행'인 것.
    pending: 공포됐지만 아직 시행 전인 판(시행예정)의 [시행일, 공포번호]."""
    name = ALIAS.get(name, name)
    d = call('lawSearch.do', {'target': 'eflaw', 'type': 'JSON', 'query': name, 'display': 100, 'nw': '2,3'})  # 2 시행예정, 3 현행(연혁 판은 빼야 100개 안에 든다)
    laws = as_list(d.get('LawSearch', {}).get('law'))
    same = [x for x in laws if x.get('법령명한글') == name]
    hit = [x for x in same if x.get('현행연혁코드') == '현행']
    if not hit:
        raise LookupError(f'현행 법령을 못 찾음: {name}')
    x = max(hit, key=lambda x: x.get('시행일자', ''))
    pending = sorted([x2.get('시행일자'), x2.get('공포번호')] for x2 in same if x2.get('현행연혁코드') == '시행예정')
    return {'id': x['법령ID'], 'mst': x['법령일련번호'], 'ef': x['시행일자'], 'kind': x.get('법령구분명', ''), 'pending': pending}


def fetch_full(cur, cache):
    """오늘 시행 중인 글(시행일 법령 eflaw, 법령ID + 현행 시행일). 그냥 '현행'(target=law) 응답에는
    공포됐지만 아직 시행 전인 항이 섞여 온다(행정소송법 제10조 제3항, 2028. 3. 1. 시행). cache에 둔다."""
    p = Path(cache) / f"eflaw-{cur['id']}-{cur['ef']}.json"
    if p.exists() and p.stat().st_size > 1000:
        return json.loads(p.read_text(encoding='utf-8'))
    d = call('lawService.do', {'target': 'eflaw', 'ID': cur['id'], 'efYd': cur['ef'], 'type': 'JSON'})
    if '법령' not in d:
        raise LookupError(f"시행일 법령 응답이 비었음: {cur}")
    p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    time.sleep(0.5)
    return d


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def lines_of(x):
    """API 글 칸을 줄 목록으로 펼친다."""
    if isinstance(x, str):
        return x.split('\n')
    return [y for z in as_list(x) for y in lines_of(z)]


def text_of(x):
    """API 글 칸은 문자열이거나 (겹친) 목록이다. 줄을 이어 하나의 글로."""
    if isinstance(x, str):
        return x
    return ' '.join(text_of(y) for y in as_list(x))


def clean(t, notes):
    """글에서 개정 표시를 떼어 notes로. 앞뒤 공백 정리."""
    for m in NOTE.finditer(t):
        notes.append(m.group(0).strip())
    return re.sub(r'\s+', ' ', NOTE.sub(' ', t)).strip()


def shape_unit(u):
    notes = []
    head = HEAD.match(u.get('조문내용', '').strip())
    body = u.get('조문내용', '').strip()[head.end():] if head else u.get('조문내용', '').strip()
    paras = []
    hangs = as_list(u.get('항'))
    for h in hangs:
        txt = text_of(h.get('항내용', ''))
        no = None
        num = (h.get('항번호') or '').strip()
        txt = txt.strip()
        big = re.match(r'^<(\d+)>', num)  # ⑳ 넘는 항(또는 일부 법령의 16항 이상)은 '<16>' 꼴로 온다
        if num and num[0] in CIRCLED:
            no = CIRCLED.index(num[0]) + 1
            if txt[:1] == num[0]:
                txt = txt[1:]
        elif big:
            no = int(big.group(1))
            txt = re.sub(r'^<%s>\s*' % big.group(1), '', txt)
        p = {'no': no, 'text': clean(txt, notes)}
        if no is None and not p['text']:
            p['text'] = clean(body, notes)  # 항 없이 호만 있는 조문(민법 제840조처럼): 조문 첫 글이 머리말
        for ho in as_list(h.get('호')):
            hraw = text_of(ho.get('호내용', '')).strip()
            hm = re.match(r'^(\d+(?:의\d+)?)\.\s*', hraw)  # 가지 호(8의2)는 호번호 칸에 '8.'만 올 때가 있어 글에서 읽는다
            hn = hm.group(1) if hm else re.sub(r'\.$', '', (ho.get('호번호') or '').strip())
            ht = hraw[hm.end():] if hm else hraw
            hd = {'no': hn, 'text': clean(ht, notes)}
            for mok in as_list(ho.get('목')):
                mn = re.sub(r'\.$', '', (mok.get('목번호') or '').strip())
                lines = [x.strip() for x in lines_of(mok.get('목내용', '')) if x.strip()]
                main = [x for x in lines if not re.match(r'^\d+\)', x)]
                subs = [re.match(r'^(\d+)\)\s*(.*)$', x) for x in lines if re.match(r'^\d+\)', x)]
                mt = re.sub(r'^\s*[가-힣]\.\s*', '', ' '.join(main))
                md = {'no': mn, 'text': clean(mt, notes)}
                for m in subs:  # 세목 1)·2)·3)은 웹 임시본처럼 sub로 나눈다
                    md.setdefault('sub', []).append({'no': m.group(1), 'text': clean(m.group(2), notes)})
                hd.setdefault('mok', []).append(md)
            p.setdefault('ho', []).append(hd)
        paras.append(p)
    if not hangs:
        paras.append({'no': None, 'text': clean(body, notes)})
    ref = u.get('조문참고자료')
    for r in as_list(ref):
        if isinstance(r, str) and r.strip():
            notes.extend(x.strip() for x in re.findall(r'\[[^\]]+\]', r) or [r.strip()])
    return {'title': (u.get('조문제목') or '').strip(), 'paras': paras, 'notes': notes}


def shape_law(d):
    law = d['법령']
    info = law['기본정보']
    arts = {}
    for u in as_list(law.get('조문', {}).get('조문단위')):
        if u.get('조문여부') != '조문':
            continue
        key = u['조문번호'] + (f"의{u['조문가지번호']}" if u.get('조문가지번호') else '')
        arts[key] = shape_unit(u)
    kind = info.get('법종구분')
    kind = kind.get('content', '') if isinstance(kind, dict) else (kind or '')
    ef, pd = info.get('시행일자', ''), info.get('공포일자', '')
    dot = lambda s: f'{s[:4]}. {int(s[4:6])}. {int(s[6:])}.' if len(s) == 8 else s
    header = f"[시행 {dot(ef)}] [{kind} 제{info.get('공포번호', '')}호, {dot(pd)}, {info.get('제개정구분', '')}]"
    return {'law': info.get('법령명_한글'), 'efYd': ef, 'header': header, 'articles': arts}


def split_jo(jo):
    m = re.fullmatch(r'(\d+)(?:의(\d+))?', str(jo))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (10 ** 6, 0)


DATE_MARK = re.compile(r'<[^>]*\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\.?\s*>|\[[^\]]*\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\.?[^\]]*\]')


def norm(t):
    """대조용 글: 개정·삭제 날짜 표시를 빼고 띄어쓰기를 지운다."""
    t = DATE_MARK.sub('', t or '').translate(str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'"}))  # 웹은 둥근 따옴표, API는 곧은 따옴표
    return re.sub(r'\s+', '', t)


def flat(a):
    """대조용: 제목과 항·호·목 글을 순서대로 펼친다(notes 제외, norm 적용)."""
    out = [('title', norm(a.get('title', '')))]
    for p in a.get('paras', []):
        out.append((f"항{p.get('no')}", norm(p.get('text', ''))))
        for h in p.get('ho', []) or []:
            out.append((f"호{h.get('no')}", norm(h.get('text', ''))))
            for m in h.get('mok', []) or []:
                out.append((f"목{m.get('no')}", norm(m.get('text', ''))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ledger')
    ap.add_argument('--compare')
    ap.add_argument('--cache', default=str(Path.home() / '.cache' / 'lawgoyang-api'), help='법령 전체 응답을 두는 저장소 밖 폴더')
    ap.add_argument('--outdir')
    ap.add_argument('--show', nargs='+', metavar=('법령', '조'), help='조문 하나(또는 여럿)의 오늘 시행 중인 글을 보여 준다: --show 민사소송법 451 452')
    a = ap.parse_args()
    Path(a.cache).mkdir(parents=True, exist_ok=True)

    if a.show:
        law, jos = a.show[0], a.show[1:]
        cur = find_current(law)
        doc = shape_law(fetch_full(cur, a.cache))
        print(law, doc['header'], ('시행예정 ' + str(cur['pending'])) if cur['pending'] else '')
        for jo in jos:
            x = doc['articles'].get(jo)
            if x is None:
                print(f'제{jo}조: 현행 법령에 없음')
                continue
            print(f"제{jo}조({x['title']})")
            for p in x['paras']:
                print(f"  {'①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'[p['no'] - 1] if isinstance(p.get('no'), int) and 0 < p['no'] <= 20 else ''}{p['text']}")
                for h in p.get('ho', []) or []:
                    print(f"    {h['no']}. {h['text']}")
                    for m in h.get('mok', []) or []:
                        print(f"      {m['no']}. {m['text']}")
            if x['notes']:
                print('  ', ' '.join(x['notes']))
        return

    if a.compare:
        idx = json.loads((Path(a.compare) / 'index.json').read_text(encoding='utf-8'))
        total = same = 0
        for law, e in idx.items():
            if law.startswith('_'):
                continue
            web = json.loads((Path(a.compare) / e['file']).read_text(encoding='utf-8'))
            cur = find_current(e.get('official', law))
            api = shape_law(fetch_full(cur, a.cache))
            if cur['ef'] != web.get('efYd'):
                print(f'! {law}: 시행일 다름 웹 {web.get("efYd")} / API {cur["ef"]}')
            for jo, w in web['articles'].items():
                total += 1
                x = api['articles'].get(jo)
                if x is None:
                    print(f'✗ {law} 제{jo}조: API에 없음')
                elif flat(x) == flat(w):
                    same += 1
                else:
                    fw, fx = flat(w), flat(x)
                    diff = next((i for i in range(max(len(fw), len(fx))) if i >= len(fw) or i >= len(fx) or fw[i] != fx[i]), None)
                    print(f'✗ {law} 제{jo}조: {fw[diff] if diff is not None and diff < len(fw) else "-"} ≠ {fx[diff] if diff is not None and diff < len(fx) else "-"}')
        print(f'대조 {total}조 가운데 일치 {same}조')
        return

    led = json.loads(Path(a.ledger).read_text(encoding='utf-8'))
    want = {}
    for art in led['articles']:
        want.setdefault(art['law'], set()).add(art['article'])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    index, missing = {}, {}
    for law in sorted(want):
        try:
            cur = find_current(law)
            doc = shape_law(fetch_full(cur, a.cache))
        except Exception as err:
            missing[law] = {'articles': sorted(want[law], key=split_jo), 'why': str(err)}
            print('✗', law, err)
            continue
        jos = sorted(want[law], key=split_jo)
        got = {j: doc['articles'][j] for j in jos if j in doc['articles']}
        lost = [j for j in jos if j not in doc['articles']]
        out = {'law': law, 'id': cur['id'], 'mst': cur['mst'], 'efYd': cur['ef'], 'header': doc['header'], 'kind': cur['kind'],
               'pending': cur['pending'], 'source': 'law.go.kr Open API (DRF lawService target=eflaw, JSON)', 'articles': got}
        if lost:
            out['not_found'] = lost
            missing[law] = {'articles': lost, 'why': '현행 법령에 그 조가 없음'}
        f = outdir / f"{cur['mst']}-{cur['ef']}.json"
        f.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        index[law] = {'id': cur['id'], 'mst': cur['mst'], 'efYd': cur['ef'], 'kind': cur['kind'], 'header': doc['header'], 'file': f.name,
                      'articles': len(got), 'pending': cur['pending']}
        print(law, cur['ef'], f'조문 {len(got)}/{len(jos)}', ('없음: ' + ','.join(lost)) if lost else '', ('시행예정 ' + str(cur['pending'])) if cur['pending'] else '')
    if missing:
        index['_missing'] = missing
    (outdir / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
