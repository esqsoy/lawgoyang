#!/usr/bin/env python3
"""판례 카드(data/precedents)와 요건사실 틀(data/frames)을 검사한다. 꼴과 규칙은 data/precedents/README.md.

사용:
  python3 -I pipeline/precedent_check.py
  python3 -I pipeline/precedent_check.py --holdout 원:2024,원:2025,법:2024-2026 --holdout-cases 2009다4787,2020다223781
멈추는 것(오류)이 하나라도 있으면 종료 코드 1이다. 경고는 알리기만 한다.
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMS = {'변', '사', '노', '법', '리', '원', '행', '입', '감'}
ART = re.compile(r'^[가-힣·\s]+(법|법률|규칙|령) 제\d+조(의\d+)?( 제\d+항)?( 제\d+호)?( 본문| 단서)?$')
NO = re.compile(r'^\d{2,4}[가-힣]{1,3}\d+$')


def norm(t):
    return re.sub(r'\s+', ' ', t or '').strip()


def parse_holdout(s):
    """'원:2024,법:2024-2026' → {(시험, 해)}"""
    out = set()
    for part in filter(None, (s or '').split(',')):
        ex, yrs = part.split(':')
        a, _, b = yrs.partition('-')
        for y in range(int(a), int(b or a) + 1):
            out.add((ex.strip(), y))
    return out


ART_PARTS = re.compile(r'^(.+?) 제(\d+)조(?:의(\d+))?(?: 제(\d+)항)?')
LAW_ALIAS = {'헌법': '대한민국헌법'}


def load_laws(d):
    """{법령: {조: 항 수}}. 조문 원문은 fetch_api.py --ledger가 판례 카드·틀의 조문까지 받아 둔다."""
    d = Path(d)
    idx = json.loads((d / 'index.json').read_text(encoding='utf-8')) if (d / 'index.json').exists() else {}
    out = {}
    for law, e in idx.items():
        if law.startswith('_'):
            continue
        doc = json.loads((d / e['file']).read_text(encoding='utf-8'))
        out[law] = {jo: sum(1 for p in x.get('paras', []) if isinstance(p.get('no'), int)) for jo, x in doc['articles'].items()}
    return out


def art_problem(laws, law, jo, para):
    """현행 원문에 없으면 이유를 돌려준다."""
    law = LAW_ALIAS.get(law, law)
    if law not in laws:
        return f'{law}의 현행 원문을 받아 두지 않았다(fetch_api.py --ledger)'
    if jo not in laws[law]:
        return f'{law} 제{jo}조가 현행 원문에 없다'
    if para and laws[law][jo] and int(para) > laws[law][jo]:
        return f'{law} 제{jo}조에 제{para}항이 없다(항 {laws[law][jo]}개)'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=str(ROOT / 'data' / 'precedents'))
    ap.add_argument('--frames', default=str(ROOT / 'data' / 'frames'))
    ap.add_argument('--prec', default=str(ROOT / 'sources' / 'api' / 'prec'))
    ap.add_argument('--laws', default=str(ROOT / 'sources' / 'api' / 'laws'), help='현행 조문 원문(fetch_api.py --ledger가 받은 것)')
    ap.add_argument('--holdout', default='', help="맞히기 구간 출제: '원:2024,원:2025,법:2024-2026'")
    ap.add_argument('--holdout-cases', default='', help='맞히기 구간에 쓰인 판결 번호(쉼표)')
    a = ap.parse_args()
    laws = load_laws(a.laws)
    err, warn = [], []
    holdout = parse_holdout(a.holdout)
    hcases = {x.strip() for x in a.holdout_cases.split(',') if x.strip()}

    frames = {}
    for p in sorted(Path(a.frames).glob('*.json')) if Path(a.frames).exists() else []:
        f = json.loads(p.read_text(encoding='utf-8'))
        frames[f.get('id')] = f
        if p.stem != f.get('id'):
            err.append(f'{p.name}: 파일 이름과 id가 다르다({f.get("id")})')
    cards = {}
    for p in sorted(Path(a.cards).glob('*.json')):
        c = json.loads(p.read_text(encoding='utf-8'))
        cards[c.get('id')] = (p, c)

    def asked_all(c):
        return (c.get('asked') or []) + [x for rp in c.get('rule_parts') or [] for x in rp.get('asked') or []]

    def legit(c, seen=()):
        """맞히기 구간 밖(만들기 구간)에 근거가 있는 카드. 그런 카드는 맞히기 구간 판결과 겹쳐도 정당하다.
        ① 만들기 구간의 공식 기출에 나왔거나, ② 구별·최근 카드로서 검색어(searched)가 있고 정당한 카드의 turn이 가리킨다."""
        if any((h.get('exam'), int(h.get('year') or 0)) not in holdout for h in asked_all(c)):
            return True
        if c.get('role') in ('구별', '최근') and c.get('searched') and c.get('id') not in seen:
            return any(t.get('ref') == c.get('id') and legit(o, seen + (c.get('id'),))
                       for _, o in cards.values() for t in o.get('turn') or [])
        return False

    overlap = 0
    for cid, (p, c) in cards.items():
        tag = p.name
        case = c.get('case') or {}
        no, hold = case.get('no', ''), str(c.get('holding', ''))
        if cid != f'{no}#{hold}':
            err.append(f'{tag}: id({cid})가 사건번호#요지번호({no}#{hold})와 다르다')
        if p.stem != (cid or '').replace('#', '-'):
            err.append(f'{tag}: 파일 이름은 {(cid or "").replace("#", "-")}.json이어야 한다')
        if 'open_turns' in c:
            err.append(f'{tag}: open_turns는 저장소에 두지 않는다(비공개 작업 폴더)')
        for k in ('found_by', 'rule', 'rule_parts', 'facts', 'result', 'articles', 'status', 'editions', 'confidence', 'checks'):
            if k not in c:
                err.append(f'{tag}: {k} 칸이 없다')
        src = Path(a.prec) / f'{no}.json'
        body = ''
        if not src.exists():
            err.append(f'{tag}: 판결 원문 {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}이 없다(fetch_api.py --full {no})')
        else:
            s = json.loads(src.read_text(encoding='utf-8'))
            body = norm(s.get('body'))
            if case.get('court') and s.get('court') and case['court'] != s['court']:
                err.append(f'{tag}: 법원이 원문({s["court"]})과 다르다')
            if case.get('date') and s.get('date') and re.sub(r'\D', '', case['date']) != re.sub(r'\D', '', s['date']):
                err.append(f'{tag}: 선고일이 원문({s["date"]})과 다르다')
        quotes_ok = bool(c.get('rule_parts'))
        for i, rp in enumerate(c.get('rule_parts') or []):
            q = norm(rp.get('quote'))
            if not q:
                err.append(f'{tag}: rule_parts[{i}] quote가 비었다'); quotes_ok = False
            elif body and q not in body:
                err.append(f'{tag}: rule_parts[{i}] quote가 판결 본문에 없다: {q[:40]}…'); quotes_ok = False
        for x in c.get('articles') or []:
            pr = art_problem(laws, x.get('law'), str(x.get('jo')), x.get('para')) if laws else None
            if pr:
                err.append(f'{tag}: articles: {pr}')
        for t in c.get('turn') or []:
            ref = (t.get('ref') or '').strip()
            if not (ref in cards or ART.match(ref)):
                err.append(f'{tag}: turn의 ref({ref or "빈칸"})가 카드 id나 조문 위치가 아니다')
            elif laws and ART.match(ref):
                m = ART_PARTS.match(ref)
                pr = art_problem(laws, m.group(1), m.group(2) + (f'의{m.group(3)}' if m.group(3) else ''), m.group(4))
                if pr:
                    err.append(f'{tag}: turn: {pr}')
            if ref.split('#')[0] in hcases and not (ref in cards and legit(cards[ref][1])):
                err.append(f'{tag}: turn이 만들기 구간 근거가 없는 맞히기 구간 판결({ref})을 가리킨다')
        for n in c.get('same_rule') or []:
            if not NO.match(n):
                warn.append(f'{tag}: same_rule 번호 꼴이 이상하다({n})')
            if n in hcases:
                warn.append(f'{tag}: same_rule에 맞히기 구간 판결({n})이 있다. 만들기 구간 검색(searched)으로 찾은 것인지 확인')
        card_keys = {(h.get('exam'), h.get('subject'), h.get('year'), str(h.get('q')), str(h.get('sub') or '')) for h in c.get('asked') or []}
        for rp in c.get('rule_parts') or []:
            for h in rp.get('asked') or []:
                if (h.get('exam'), h.get('subject'), h.get('year'), str(h.get('q')), str(h.get('sub') or '')) not in card_keys:
                    err.append(f'{tag}: 마디 asked({h.get("exam")}{h.get("year")} {h.get("subject")} 문{h.get("q")} {h.get("sub")})가 카드 asked에 없다')
        for h in asked_all(c):
            for k in ('exam', 'subject', 'year', 'q'):
                if not h.get(k):
                    err.append(f'{tag}: asked에 {k}가 없다')
            if h.get('exam') not in EXAMS:
                err.append(f'{tag}: asked의 시험({h.get("exam")})이 공식 기출 코드가 아니다')
            if (h.get('exam'), int(h.get('year') or 0)) in holdout:
                err.append(f'{tag}: asked에 맞히기 구간 출제({h.get("exam")}{h.get("year")})가 있다')
        if no in hcases:
            if legit(c):
                overlap += 1
            else:
                err.append(f'{tag}: 만들기 구간 근거 없이 맞히기 구간 판결로 만든 카드다')
        slots = c.get('slots') or ([c['slot']] if c.get('slot') else [])
        if c.get('slot') and c.get('slots'):
            err.append(f'{tag}: slot과 slots를 함께 두지 않는다(slots 하나로)')
        for sl in slots:
            fr = frames.get(sl.get('frame'))
            if not fr:
                err.append(f'{tag}: slot의 틀({sl.get("frame")})이 없다')
            elif sl.get('node') not in {n.get('id') for n in fr.get('nodes', [])}:
                err.append(f'{tag}: slot의 마디({sl.get("node")})가 틀에 없다')
        if c.get('role') and c['role'] not in ('바탕', '구별', '최근'):
            err.append(f'{tag}: role은 바탕·구별·최근 가운데 하나다({c["role"]})')
        bx = (c.get('editions') or {}).get('bar_extra')
        if bx and (bx.get('kind') not in ('반대의견', '별개의견', '원심 논리') or not (bx.get('text') or '').strip()):
            err.append(f'{tag}: bar_extra는 kind(반대의견·별개의견·원심 논리)와 text가 있어야 한다(학설 줄은 안 됨)')
        if c.get('confidence') == '확실':
            by = {x.get('by') for x in c.get('checks') or [] if x.get('result') == '확실'}
            if not {'이솝', '파핀'} <= by:
                err.append(f'{tag}: 확실인데 이솝·파핀 둘의 확실 검사가 없다')
            if not (c.get('status') or {}).get('reverse_checked'):
                err.append(f'{tag}: 확실인데 역방향 점검일(status.reverse_checked)이 없다')
            if not quotes_ok:
                err.append(f'{tag}: 확실인데 quote가 다 맞지 않는다')
        st = c.get('status') or {}
        if st.get('current') is False:
            if not st.get('overruled_by'):
                err.append(f'{tag}: current가 false인데 overruled_by가 없다')
            elif '#' in st['overruled_by'] and st['overruled_by'] not in cards:
                warn.append(f'{tag}: overruled_by({st["overruled_by"]})가 카드에 없다')
            if not st.get('scope'):
                warn.append(f'{tag}: 변경 범위(status.scope)가 없다')
        ed = c.get('editions') or {}
        if ed.get('court') and (ed.get('court_extra') or ed.get('doctrine')):
            err.append(f'{tag}: 법원판에는 학설·추가 견해 칸을 두지 않는다')

    for fid, f in frames.items():
        if f.get('module'):
            for k in ('plug', 'not_ex_officio'):
                if not f.get(k):
                    err.append(f'틀 {fid}: 모듈 틀에 {k}가 없다')
        for n in f.get('nodes', []):
            if n.get('stage') not in ('청구원인', '항변', '재항변', '재재항변', '직권조사'):
                err.append(f'틀 {fid}: 마디 {n.get("id")}의 stage({n.get("stage")})가 청구원인·항변·재항변·재재항변·직권조사가 아니다')
            basis = n.get('basis') or []
            if not basis:
                err.append(f'틀 {fid}: 마디 {n.get("id")}에 근거가 없다')
            for b in basis:
                if not (b in cards or ART.match(b) or (b in frames and frames[b].get('module'))):
                    err.append(f'틀 {fid}: 마디 {n.get("id")}의 근거({b})가 카드 id나 조문 위치가 아니다')
                elif laws and ART.match(b):
                    m = ART_PARTS.match(b)
                    pr = art_problem(laws, m.group(1), m.group(2) + (f'의{m.group(3)}' if m.group(3) else ''), m.group(4))
                    if pr:
                        err.append(f'틀 {fid}: 마디 {n.get("id")}: {pr}')

    for w in warn:
        print('경고:', w)
    for e in err:
        print('오류:', e)
    print(f'카드 {len(cards)}, 틀 {len(frames)}, 오류 {len(err)}, 경고 {len(warn)}' + (f', 맞히기 구간 판결과 겹치는 정당한 카드 {overlap}' if hcases else ''))
    sys.exit(1 if err else 0)


if __name__ == '__main__':
    main()
