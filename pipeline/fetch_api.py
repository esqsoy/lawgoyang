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
import argparse, datetime, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

DRF = 'https://www.law.go.kr/DRF/'
TODAY = datetime.date.today().isoformat()
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
    pending: 공포됐지만 아직 시행 전인 판(시행예정)의 [시행일, 공포번호, 법령일련번호]. 시행일마다 하나,
    같은 날 시행되는 판이 여럿이면 나중에 공포된 것(일련번호가 큰 것). 시행예정 판은 ID+시행일로는
    빈 응답이 오고 일련번호(MST)+시행일로만 받힌다(fetch_full by_mst)."""
    name = ALIAS.get(name, name)
    d = call('lawSearch.do', {'target': 'eflaw', 'type': 'JSON', 'query': name, 'display': 100, 'nw': '2,3'})  # 2 시행예정, 3 현행(연혁 판은 빼야 100개 안에 든다)
    laws = as_list(d.get('LawSearch', {}).get('law'))
    same = [x for x in laws if x.get('법령명한글') == name]
    hit = [x for x in same if x.get('현행연혁코드') == '현행']
    if not hit:
        raise LookupError(f'현행 법령을 못 찾음: {name}')
    x = max(hit, key=lambda x: x.get('시행일자', ''))
    by_ef = {}
    for x2 in same:
        if x2.get('현행연혁코드') != '시행예정' or not x2.get('시행일자'):
            continue
        k = x2['시행일자']
        if k not in by_ef or int(x2.get('법령일련번호') or 0) > int(by_ef[k][2] or 0):
            by_ef[k] = [k, x2.get('공포번호'), x2.get('법령일련번호')]
    pending = [by_ef[k] for k in sorted(by_ef)]
    return {'id': x['법령ID'], 'mst': x['법령일련번호'], 'ef': x['시행일자'], 'kind': x.get('법령구분명', ''), 'pending': pending}


def fetch_full(cur, cache):
    """오늘 시행 중인 글(시행일 법령 eflaw, 법령ID + 현행 시행일). 그냥 '현행'(target=law) 응답에는
    공포됐지만 아직 시행 전인 항이 섞여 온다(행정소송법 제10조 제3항, 2028. 3. 1. 시행). cache에 둔다."""
    p = Path(cache) / f"eflaw-{cur['id']}-{cur['ef']}.json"
    if p.exists() and p.stat().st_size > 1000:
        return json.loads(p.read_text(encoding='utf-8'))
    key = {'MST': cur['mst']} if cur.get('by_mst') else {'ID': cur['id']}
    d = call('lawService.do', {'target': 'eflaw', **key, 'efYd': cur['ef'], 'type': 'JSON'})
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



def prec_body(t):
    """판례내용 HTML → 글. <br>은 줄바꿈, 다른 꼬리표는 지우고, 줄마다 공백을 하나로 줄인다."""
    t = re.sub(r'<br\s*/?>', '\n', t or '', flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return '\n'.join(re.sub(r'[ \t\u00a0]+', ' ', x).strip() for x in t.split('\n')).strip()


def fetch_prec_full(no):
    """사건번호 → (저장소에 둘 기록, 전체 응답). 기록에는 판결 본문(판례내용)과 사실 칸만 둔다.
    판시사항·판결요지는 따로 headnote 칸에 출처와 함께 둔다(PRINCIPLES 4, 26.11.28). 받은 뒤 `python3 -I pipeline/verify_machine.py --headnotes`를 돌린다."""
    tgt = 'detc' if '헌' in no else 'prec'
    root, key, sid = {'prec': ('PrecSearch', 'prec', '판례일련번호'), 'detc': ('DetcSearch', 'Detc', '헌재결정례일련번호')}[tgt]
    same = lambda x: re.sub(r'\s+', '', x.get('사건번호', '')) == no
    found = []
    for params in ([{'nb': no}] if tgt == 'prec' else []) + [{'query': no, 'display': 100}]:
        found = [x for x in as_list(call('lawSearch.do', {'target': tgt, 'type': 'JSON', 'display': 20, **params}).get(root, {}).get(key)) if same(x)]
        if found:
            break
    if not found:
        raise LookupError('law.go.kr에서 못 찾음')
    raw = call('lawService.do', {'target': tgt, 'ID': found[0][sid], 'type': 'JSON'})
    x = raw.get('PrecService') or raw.get('DetcService') or {}
    body = prec_body(x.get('판례내용') or x.get('전문'))
    if not body:
        raise LookupError('본문이 비었음')
    rec = {'no': no, 'serial': found[0][sid], 'court': x.get('법원명') or ('헌법재판소' if tgt == 'detc' else ''),
           'date': x.get('선고일자') or x.get('종국일자') or '', 'kind': x.get('판결유형') or x.get('사건종류명') or '',
           'name': x.get('사건명') or '', 'refs_articles': prec_body(x.get('참조조문')), 'refs_cases': prec_body(x.get('참조판례')),
           'fetched': TODAY, 'source': f"law.go.kr Open API {tgt} {found[0][sid]}", 'body': body}
    return rec, raw

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
    ap.add_argument('--rule', nargs='+', metavar='검색어', help='대법원 예규(등기예규·재판예규)와 행정규칙을 이름으로 찾는다(현행 먼저): --rule 상속재산 협의분할')
    ap.add_argument('--rule-id', nargs='+', metavar='일련번호', help='행정규칙(예규) 본문을 보여 준다(--rule 결과의 일련번호)')
    ap.add_argument('--prec-search', nargs='+', metavar='검색어', help='판결·결정을 키워드로 찾는다(사건명 먼저, 없으면 본문): --prec-search 퇴거 인도 처분권주의')
    ap.add_argument('--body', action='store_true', help='--prec-search를 처음부터 본문 검색으로')
    ap.add_argument('--until', metavar='YYYYMMDD', help='--prec-search 결과에서 이 날짜 뒤에 선고된 판결·결정을 숨긴다(맞히기 구간 보호): --until 20231231')
    ap.add_argument('--full', nargs='+', metavar='사건번호', help='판결 원문(판례내용)을 받아 sources/api/prec/<번호>.json에 둔다. 판시사항·요지 등 전체 응답은 --cache에만 둔다: --full 2009다4787')
    ap.add_argument('--force-full', action='store_true', help='--full이 이름을 가린(redacted) 본문도 덮어쓴다')
    ap.add_argument('--prec-dir', default=str(Path(__file__).resolve().parent.parent / 'sources' / 'api' / 'prec'))
    ap.add_argument('--case', nargs='+', metavar='사건번호', help='판결·결정을 사건번호로 찾아 판시사항·요지·참조조문·주문을 보여 준다: --case 2023다240299 2017헌가16')
    ap.add_argument('--show', nargs='+', metavar=('법령', '조'), help='조문 하나(또는 여럿)의 오늘 시행 중인 글을 보여 준다: --show 민사소송법 451 452')
    a = ap.parse_args()
    Path(a.cache).mkdir(parents=True, exist_ok=True)

    if a.rule:
        q = ' '.join(a.rule)
        xs = []
        for search in (1, 2):  # 1 이름, 2 본문
            d = call('lawSearch.do', {'target': 'admrul', 'type': 'JSON', 'query': q, 'display': 50, 'search': search})
            xs = as_list(d.get('AdmRulSearch', {}).get('admrul'))
            if xs:
                break
        xs.sort(key=lambda x: (x.get('현행연혁구분') != '현행', -int(x.get('발령일자') or 0)))
        print(f"== '{q}' {'이름' if search == 1 else '본문'} 검색 {len(xs)}건(현행 먼저, 50건까지)")
        for x in xs[:20]:
            print(f"[{x.get('현행연혁구분')}] {x.get('행정규칙종류')} 제{x.get('발령번호')}호 {x.get('발령일자')} {x.get('행정규칙명')} (일련번호 {x.get('행정규칙일련번호')})")
        return

    if a.rule_id:
        for sid in a.rule_id:
            d = call('lawService.do', {'target': 'admrul', 'ID': sid, 'type': 'JSON'}).get('AdmRulService', {})
            b = d.get('행정규칙기본정보', {})
            print(f"== {b.get('행정규칙종류')} 제{b.get('발령번호')}호 {b.get('행정규칙명')} 발령 {b.get('발령일자')} 현행 {b.get('현행여부')} ({b.get('소관부처명')})")
            body = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text_of(d.get('조문내용', '')))).strip()
            print(body)  # 자르지 않는다(긴 예규의 뒤 조항을 놓친 일이 있었다, 26.11.13)
        return

    if a.prec_search:
        # 사건번호를 모를 때(26.11.24 하위 작업이 짚음). 대법원·전원합의체·최근 먼저. 찾은 번호는 --case로 원문을 본다.
        q = ' '.join(a.prec_search)
        for tgt, root, key in (('prec', 'PrecSearch', 'prec'), ('detc', 'DetcSearch', 'Detc')):
            xs, how = [], ''
            for search in ([2] if a.body else [1, 2]):
                d = call('lawSearch.do', {'target': tgt, 'type': 'JSON', 'query': q, 'display': 50, 'search': search})
                xs = as_list(d.get(root, {}).get(key))
                how = '이름' if search == 1 else '본문'
                if xs:
                    break
            if a.until:
                lim = re.sub(r'\D', '', a.until)
                hidden = [x for x in xs if re.sub(r'\D', '', x.get('선고일자') or x.get('종국일자') or '') > lim]
                xs = [x for x in xs if x not in hidden]
                if hidden:
                    print(f'== {lim} 뒤 선고 {len(hidden)}건은 숨김(--until)')
            if tgt == 'prec':
                xs.sort(key=lambda x: (x.get('법원명') != '대법원', '전원합의체' not in (x.get('판결유형') or ''),
                                       -int(re.sub(r'\D', '', x.get('선고일자') or '') or 0)))
            print(f"== {'판례' if tgt == 'prec' else '헌재'} '{q}' {how} 검색 {len(xs)}건(50건까지)")
            for x in xs[:20]:
                print(f"{x.get('사건번호')} {x.get('법원명') or ('헌법재판소' if tgt == 'detc' else (x.get('데이터출처명') or '법원명 없음'))} {x.get('선고일자') or x.get('종국일자') or ''} {x.get('판결유형') or ''} {(x.get('사건명') or '')[:80]}")
        return

    if a.full:
        outdir = Path(a.prec_dir); outdir.mkdir(parents=True, exist_ok=True)
        for no in a.full:
            no = re.sub(r'\s+', '', no)
            old = outdir / f'{no}.json'
            if old.exists() and json.loads(old.read_text(encoding='utf-8')).get('redacted') and not a.force_full:
                print(f'== {no}: 이름을 가린 본문이 이미 있어 덮지 않는다(--force-full로 덮으면 가림이 사라진다)')
                continue
            try:
                rec, raw = fetch_prec_full(no)
            except LookupError as e:
                print(f'== {no}: {e}')
                continue
            Path(a.cache).mkdir(parents=True, exist_ok=True)
            (Path(a.cache) / f'prec-{no}.json').write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
            (outdir / f'{no}.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f"== {no} {rec['court']} {rec['date']} {rec['kind']} 본문 {len(rec['body'])}자 → {outdir / (no + '.json')}")
        return

    if a.case:
        for no in a.case:
            tgt = 'detc' if '헌' in no else 'prec'
            root, key, sid = {'prec': ('PrecSearch', 'prec', '판례일련번호'), 'detc': ('DetcSearch', 'Detc', '헌재결정례일련번호')}[tgt]
            same = lambda x: re.sub(r'\s+', '', x.get('사건번호', '')) == re.sub(r'\s+', '', no)
            found = []
            # 판례는 사건번호 칸(nb)으로 찾아야 정확하다. query는 사건명·본문을 봐서 '무'·'마' 사건(2015무26 등)을 놓친다.
            for params in ([{'nb': no}] if tgt == 'prec' else []) + [{'query': no, 'display': 100}, {'query': no, 'display': 100, 'page': 2}]:
                found = [x for x in as_list(call('lawSearch.do', {'target': tgt, 'type': 'JSON', 'display': 20, **params}).get(root, {}).get(key)) if same(x)]
                if found:
                    break
            if not found:
                print(f'== {no}: law.go.kr에서 못 찾음')
                continue
            d = call('lawService.do', {'target': tgt, 'ID': found[0][sid], 'type': 'JSON'})
            x = d.get('PrecService') or d.get('DetcService') or {}
            strip = lambda t: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t or '')).strip()
            print(f"== {x.get('사건번호')} {x.get('법원명') or ('헌법재판소' if tgt == 'detc' else (x.get('데이터출처명') or '법원명 없음'))} {x.get('선고일자') or x.get('종국일자')} {x.get('판결유형', '')} {x.get('사건명', '')}")
            for f in ('판시사항', '판결요지', '결정요지', '참조조문', '심판대상조문', '참조판례'):
                if x.get(f):
                    print(f'[{f}] ' + strip(x[f])[:1500])
            body = strip(x.get('판례내용') or x.get('전문'))
            m = re.search(r'【?\[?\s*주\s*문\s*\]?】?(.{0,400})', body)
            if m:
                print('[주문] ' + m.group(1))
        return

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
    # 카드가 인용한 조문도 받는다(원장 밖 조문, 원문이 없어 pending으로 둔 조문). 세트 폴더는 원장 옆 data/sets.
    sets_dir = Path(a.ledger).resolve().parent.parent / 'sets'
    for f in sorted(sets_dir.glob('*.json')):
        st = json.loads(f.read_text(encoding='utf-8'))
        for iss in st.get('issues', []):
            for c in iss.get('cites', []):
                want.setdefault(c['law'], set()).add(str(c['jo']))
    # 판례 카드의 articles와 틀 마디·turn의 조문 위치도 받는다(26.11.28: 카드 조문이 현행 법령에 있는지 검사기가 대조한다).
    data_dir = Path(a.ledger).resolve().parent.parent
    art_ref = re.compile(r'^(.+?) 제(\d+)조(?:의(\d+))?')
    def add_ref(t):
        m = art_ref.match(t or '')
        if m:
            want.setdefault(ALIAS.get(m.group(1), m.group(1)), set()).add(m.group(2) + (f'의{m.group(3)}' if m.group(3) else ''))
    for f in sorted((data_dir / 'precedents').glob('*.json')):
        c = json.loads(f.read_text(encoding='utf-8'))
        for x in c.get('articles') or []:
            want.setdefault(x['law'], set()).add(str(x['jo']))
        for t in c.get('turn') or []:
            add_ref(t.get('ref'))
    for f in sorted((data_dir / 'frames').glob('*.json')):
        for n in json.loads(f.read_text(encoding='utf-8')).get('nodes', []):
            for b in n.get('basis') or []:
                add_ref(b)
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
        out = {'law': law, 'id': cur['id'], 'mst': cur['mst'], 'efYd': cur['ef'], 'header': doc['header'], 'kind': cur['kind'], 'fetched': TODAY,
               'pending': cur['pending'], 'source': 'law.go.kr Open API (DRF lawService target=eflaw, JSON)', 'articles': got}
        if lost:
            out['not_found'] = lost
            missing[law] = {'articles': lost, 'why': '현행 법령에 그 조가 없음'}
        f = outdir / f"{cur['mst']}-{cur['ef']}.json"
        if f.exists():  # 같은 판·같은 글이면 처음 받은 날을 그대로 둔다(다시 받아도 diff가 생기지 않게)
            old = json.loads(f.read_text(encoding='utf-8'))
            if old.get('articles') == got and old.get('pending') == cur['pending']:
                out['fetched'] = old.get('fetched', TODAY)
        f.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        index[law] = {'id': cur['id'], 'mst': cur['mst'], 'efYd': cur['ef'], 'kind': cur['kind'], 'header': doc['header'], 'file': f.name,
                      'articles': len(got), 'pending': cur['pending']}
        print(law, cur['ef'], f'조문 {len(got)}/{len(jos)}', ('없음: ' + ','.join(lost)) if lost else '', ('시행예정 ' + str(cur['pending'])) if cur['pending'] else '')
    if missing:
        index['_missing'] = missing
    (outdir / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
