#!/usr/bin/env python3
"""주기 업데이트 점검(PRINCIPLES 2-1): 법령 개정, 시행 예정 개정, 새 전원합의체 판결, 헌재 위헌 결정을
우리 조문(원장 외울 조문 + 세트 카드 조문)과 카드 판결에 맞춰 보고서를 쓴다. 카드는 고치지 않는다.

사용:
  python3 -I pipeline/update_check.py [--since 20261001] [--ahead 120] [--cache <저장소 밖 폴더>]
    --since: 판례·결정을 이 날부터 본다(기본: data/updates/last.json의 마지막 점검일, 없으면 30일 전).
    --ahead: 시행 예정 개정을 오늘부터 이 날수 안의 것만 본다(기본 120일).
  결과: data/updates/<오늘>.md, <오늘>.json, last.json(마지막 점검일).

찾는 것.
- 법령: sources/api/laws/index.json에 적힌 시행일과 지금 현행 시행일이 다르면, 그 법령의 우리 조문을 새 원문과 대조해
  바뀐 조문(문언 바뀜·없어짐)을 적는다. 고치려면 fetch_api.py --ledger 로 다시 받고 빌드한다(바뀐 카드는 빌드가 멈춘다).
- 시행 예정: 공포됐지만 아직 시행 전인 판(pending)을 받아 우리 조문이 어떻게 바뀌는지 적는다('○○부터 바뀜').
- 판례: 기간 안 대법원 전원합의체 판결의 참조조문을 우리 조문과, '(변경)'으로 적힌 판례를 카드 판결과 맞춘다.
- 헌재: 우리 법령 이름으로 기간 안 결정을 찾아, 주문이 위헌·헌법불합치·한정위헌이고 심판대상조문이 우리 조문이면 적는다.
"""
import argparse, datetime, importlib.util, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('fetch_api', ROOT / 'pipeline' / 'fetch_api.py')
fa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fa)

TODAY = datetime.date.today()
NAMES = {'대한민국헌법': '헌법'}
ART = re.compile(r'(?:(?P<law>[가-힣][가-힣ㆍ·\s]*?(?:법|령|규칙|규정|헌법))\s*)?제\s*(?P<jo>\d+)\s*조(?:\s*의\s*(?P<br>\d+))?')


def ymd(d):
    return d.strftime('%Y%m%d')


def our_targets():
    """우리 조문 {(법령, 조)}, 카드 판결 사건번호 {번호: [세트]}, 카드가 있는 조문 {(법령, 조): [세트]}."""
    arts, cards, on_cards = set(), {}, {}
    led = ROOT / 'data' / 'ledger' / 'ledger-v1.json'
    if not led.exists():
        led = ROOT / 'data' / 'ledger' / 'ledger-v0.json'
    for a in json.loads(led.read_text(encoding='utf-8'))['articles']:
        arts.add((a['law'], a['article']))
    for f in sorted((ROOT / 'data' / 'sets').glob('*.json')):
        st = json.loads(f.read_text(encoding='utf-8'))
        for iss in st['issues']:
            for c in iss['cites']:
                arts.add((c['law'], str(c['jo'])))
                on_cards.setdefault((c['law'], str(c['jo'])), set()).add((st['id'], c.get('para')))
                for p in c.get('precedent', []):
                    cards.setdefault(re.sub(r'\s+', '', p.get('no', '')), set()).add(st['id'])
        for b in st.get('basis', []):
            if b.get('no'):
                cards.setdefault(re.sub(r'\s+', '', b['no']), set()).add(st['id'])
    return arts, {k: sorted(v) for k, v in cards.items() if k}, {k: sorted(v) for k, v in on_cards.items()}


def parse_articles(text, default_law=None):
    """'[1] 헌법 제12조 제1항, 제21조, 군형법 제64조' → [(헌법,12),(헌법,21),(군형법,64)]. '같은 법'은 앞 법령."""
    out, law = [], default_law
    text = re.sub(r'<[^>]+>', ' ', text or '').replace('같은 법', '').replace('구 ', '')
    for m in ART.finditer(text):
        if m.group('law'):
            law = re.sub(r'^\s*(?:\[\d+\]\s*)?', '', m.group('law')).strip()
            law = NAMES.get(law, law)
        if law:
            out.append((law, m.group('jo') + (f"의{m.group('br')}" if m.group('br') else '')))
    return out


def search_all(target, params, cap=500):
    items, page = [], 1
    root = {'prec': 'PrecSearch', 'detc': 'DetcSearch'}[target]
    key = {'prec': 'prec', 'detc': 'Detc'}[target]
    while len(items) < cap:
        d = fa.call('lawSearch.do', {'target': target, 'type': 'JSON', 'display': 100, 'page': page, **params})
        s = d.get(root, {})
        got = fa.as_list(s.get(key))
        items += got
        if len(got) < 100:
            break
        page += 1
        time.sleep(0.3)
    return items


def detail(target, sid, cache):
    p = Path(cache) / f'{target}-{sid}.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    d = fa.call('lawService.do', {'target': target, 'ID': sid, 'type': 'JSON'})
    p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    time.sleep(0.3)
    return d


def word_diff(a, b, ctx=20, cap=600):
    """바뀐 곳만 글자 단위로: …앞[-지금-]{+바뀜+}뒤…, 앞뒤 ctx글자. fa.flat은 띄어쓰기를 지운 글이라 어절이 아니라 글자로 본다."""
    import difflib
    x, y = ('¶'.join(t for _, t in v) if isinstance(v, list) else v for v in (a, b))  # fa.flat: [(자리, 글)]
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=x, b=y, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        out.append('…' + x[max(0, i1 - ctx):i1] + (f'[-{x[i1:i2]}-]' if i2 > i1 else '') + (f'{{+{y[j1:j2]}+}}' if j2 > j1 else '') + x[i2:i2 + ctx] + '…')
    s = ' / '.join(out)
    return s if len(s) <= cap else s[:cap] + '…'


def changed_paras(a, b):
    """두 판의 같은 조에서 글이 달라진 항 번호(호·목 포함, 새로 생기거나 없어진 항 포함). 항 없는 조는 [None]."""
    def per(x):
        out = {}
        for p in x.get('paras', []):
            out[p.get('no')] = fa.flat({'paras': [p]})
        return out
    pa, pb = per(a), per(b)
    return sorted({k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)}, key=lambda k: (k is not None, k or 0))


def check_laws(arts, ahead, cache):
    idx_path = ROOT / 'sources' / 'api' / 'laws' / 'index.json'
    idx = json.loads(idx_path.read_text(encoding='utf-8'))
    ours = {}
    for law, jo in arts:
        ours.setdefault(law, set()).add(jo)
    changed, upcoming, errors = [], [], []
    for law, e in sorted(idx.items()):
        if law.startswith('_'):
            continue
        try:
            cur = fa.find_current(law)
        except Exception as err:
            errors.append({'law': law, 'error': str(err)})
            continue
        mine = sorted(ours.get(law, set()), key=fa.split_jo)
        now = fa.shape_law(fa.fetch_full(cur, cache))
        if cur['ef'] != e['efYd']:
            old = json.loads((idx_path.parent / e['file']).read_text(encoding='utf-8'))['articles']
            for jo in mine:
                if jo not in old:
                    continue
                if jo not in now['articles']:
                    changed.append({'law': law, 'jo': jo, 'kind': '없어짐', 'from': e['efYd'], 'to': cur['ef']})
                elif fa.flat(now['articles'][jo]) != fa.flat(old[jo]):
                    changed.append({'law': law, 'jo': jo, 'kind': '문언 바뀜', 'from': e['efYd'], 'to': cur['ef'],
                                    'paras': changed_paras(old[jo], now['articles'][jo]),
                                    'diff': word_diff(fa.flat(old[jo]), fa.flat(now['articles'][jo]))})
        for ef, no, mst in cur['pending']:
            if not ef or datetime.datetime.strptime(ef, '%Y%m%d').date() > TODAY + datetime.timedelta(days=ahead):
                continue
            try:
                fut = fa.shape_law(fa.fetch_full({'id': cur['id'], 'ef': ef, 'mst': mst, 'by_mst': True}, cache))
            except Exception as err:
                errors.append({'law': law, 'pending': ef, 'error': str(err)})
                continue
            for jo in mine:
                a, b = now['articles'].get(jo), fut['articles'].get(jo)
                if a and not b:
                    upcoming.append({'law': law, 'jo': jo, 'kind': '없어짐', 'from': ef, 'promulgation': no})
                elif a and b and fa.flat(a) != fa.flat(b):
                    upcoming.append({'law': law, 'jo': jo, 'kind': '문언 바뀜', 'from': ef, 'promulgation': no,
                                     'paras': changed_paras(a, b), 'diff': word_diff(fa.flat(a), fa.flat(b))})
        time.sleep(0.2)
    return changed, upcoming, errors


def check_precedents(arts, cards, since, cache):
    hits = []
    rng = f'{ymd(since)}~{ymd(TODAY)}'
    for x in search_all('prec', {'query': '전원합의체', 'search': 2, 'prncYd': rng}):
        d = detail('prec', x['판례일련번호'], cache).get('PrecService', {})
        if '전원합의체' not in (d.get('판결유형') or ''):
            continue
        refs = parse_articles(d.get('참조조문'))
        mine = sorted({r for r in refs if r in arts})
        changed_no = [re.sub(r'\s+', '', m) for m in re.findall(r'선고\s*([0-9]{2,4}[가-힣]{1,3}[0-9]+)\s*[^,(<]*\(변경\)', d.get('참조판례') or '')]
        on_cards = {n: cards[n] for n in changed_no if n in cards}
        hits.append({'no': d.get('사건번호'), 'date': d.get('선고일자'), 'name': d.get('사건명'), 'kind': d.get('판결유형'),
                     'our_articles': [f'{l} 제{j}조' for l, j in mine], 'overruled': changed_no, 'overruled_on_cards': on_cards})
    return hits


def check_ccourt(arts, since, cache):
    laws = sorted({l for l, _ in arts})
    rng = f'{ymd(since)}~{ymd(TODAY)}'
    seen, hits = set(), []
    for law in laws:
        q = '대한민국헌법' if law == '헌법' else law
        for x in search_all('detc', {'query': q, 'edYd': rng}, cap=200):
            sid = x['헌재결정례일련번호']
            if sid in seen:
                continue
            seen.add(sid)
            d = detail('detc', sid, cache).get('DetcService', {})
            full = re.sub(r'<[^>]+>', ' ', d.get('전문') or '')
            m = re.search(r'\[\s*주\s*문\s*\](.*?)\[\s*이\s*유\s*\]', full, re.S)
            order = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
            if not re.search(r'헌법에 (?:위반|합치되지)|위헌', order):
                continue
            targets = parse_articles(d.get('심판대상조문') or '') + parse_articles(d.get('사건명') or '')
            mine = sorted({t for t in targets if t in arts})
            if mine:
                hits.append({'no': d.get('사건번호'), 'date': d.get('종국일자'), 'name': d.get('사건명'), 'order': order[:200],
                             'our_articles': [f'{l} 제{j}조' for l, j in mine]})
        time.sleep(0.2)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since')
    ap.add_argument('--ahead', type=int, default=120)
    ap.add_argument('--cache', default=str(Path.home() / '.cache' / 'lawgoyang-api'))
    a = ap.parse_args()
    Path(a.cache).mkdir(parents=True, exist_ok=True)
    out = ROOT / 'data' / 'updates'
    out.mkdir(parents=True, exist_ok=True)
    last = out / 'last.json'
    if a.since:
        since = datetime.datetime.strptime(a.since, '%Y%m%d').date()
    elif last.exists():
        since = datetime.date.fromisoformat(json.loads(last.read_text(encoding='utf-8'))['checked'])
    else:
        since = TODAY - datetime.timedelta(days=30)

    arts, cards, on_cards = our_targets()
    changed, upcoming, errors = check_laws(arts, a.ahead, a.cache)
    for c in changed + upcoming:
        cs = on_cards.get((c['law'], c['jo']), [])
        hit = [(sid, pa) for sid, pa in cs if 'paras' not in c or pa is None or pa in c['paras'] or None in c['paras']]
        c['sets'] = sorted({sid for sid, _ in hit})
        c['sets_other_paras'] = sorted({sid for sid, _ in cs} - set(c['sets']))
    pn = lambda c: (' 바뀐 항: ' + ', '.join('항 없음' if x is None else f'제{x}항' for x in c['paras']) + '.') if c.get('paras') else ''
    card_mark = lambda c: pn(c) + (f" 카드 있음: {', '.join(c['sets'])}" if c['sets'] else ' 그 항의 카드 없음') + (f" (같은 조 다른 항 카드: {', '.join(c['sets_other_paras'])})" if c.get('sets_other_paras') else '')
    precs = check_precedents(arts, cards, since, a.cache)
    ccourt = check_ccourt(arts, since, a.cache)

    rep = {'checked': TODAY.isoformat(), 'since': since.isoformat(), 'our_articles': len(arts), 'card_precedents': len(cards),
           'laws_changed': changed, 'laws_upcoming': upcoming, 'en_banc': precs, 'ccourt': ccourt, 'errors': errors}
    (out / f'{TODAY.isoformat()}.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    L = [f'# 주기 업데이트 점검 {TODAY.isoformat()}', '',
         f'판례·결정은 {since.isoformat()}부터, 시행 예정 개정은 {a.ahead}일 안. 우리 조문 {len(arts)}개, 카드 판결 {len(cards)}건과 맞췄다. 카드는 고치지 않았다.', '']
    L += ['## 바뀐 조문(이미 시행)', '']
    L += [f"- {c['law']} 제{c['jo']}조: {c['kind']} ({c['from']} → {c['to']})" + card_mark(c) + (f"\n  - {c['diff']}" if c.get('diff') else '') for c in changed] or ['- 없음']
    L += ['', '## 시행 예정으로 바뀌는 조문', '']
    L += [f"- {c['law']} 제{c['jo']}조: {c['kind']}, {c['from'][:4]}. {int(c['from'][4:6])}. {int(c['from'][6:])}.부터(공포번호 {c['promulgation']})" + card_mark(c) + (f"\n  - {c['diff']}" if c.get('diff') else '') for c in upcoming] or ['- 없음']
    L += ['', '## 전원합의체 판결', '']
    rel = [p for p in precs if p['our_articles'] or p['overruled_on_cards']]
    only_const = lambda p: not p['overruled_on_cards'] and all(x.startswith('헌법 ') for x in p['our_articles'])
    main_rel = [p for p in rel if not only_const(p)]
    const_rel = [p for p in rel if only_const(p)]
    L += [f"- {p['date']} {p['no']} {p['name'][:60]}: 우리 조문 {', '.join(p['our_articles']) or '-'}"
          + (f"; **카드 판결 변경 {p['overruled_on_cards']}**" if p['overruled_on_cards'] else '') for p in main_rel] or ['- 우리 조문(헌법 말고)·카드와 겹치는 것 없음']
    if const_rel:
        L += [f"- 헌법 조문만 참조조문에서 겹침 {len(const_rel)}건: " + ', '.join(f"{p['no']}({p['name'].split('[')[0][:20]})" for p in const_rel)]
    L += [f'(기간 안 전원합의체 판결 {len(precs)}건 가운데 겹치는 것 {len(rel)}건)', '']
    L += ['## 헌재 위헌·헌법불합치 결정', '']
    L += [f"- {h['date']} {h['no']} {h['name']}: {', '.join(h['our_articles'])} — {h['order'][:120]}" for h in ccourt] or ['- 우리 조문과 겹치는 것 없음']
    if errors:
        L += ['', '## 받지 못한 것', ''] + [f"- {e}" for e in errors]
    (out / f'{TODAY.isoformat()}.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    last.write_text(json.dumps({'checked': TODAY.isoformat()}, ensure_ascii=False) + '\n', encoding='utf-8')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
