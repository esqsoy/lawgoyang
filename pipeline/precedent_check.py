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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=str(ROOT / 'data' / 'precedents'))
    ap.add_argument('--frames', default=str(ROOT / 'data' / 'frames'))
    ap.add_argument('--prec', default=str(ROOT / 'sources' / 'api' / 'prec'))
    ap.add_argument('--holdout', default='', help="맞히기 구간 출제: '원:2024,원:2025,법:2024-2026'")
    ap.add_argument('--holdout-cases', default='', help='맞히기 구간에 쓰인 판결 번호(쉼표)')
    a = ap.parse_args()
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
        for t in c.get('turn') or []:
            ref = (t.get('ref') or '').strip()
            if not (ref in cards or ART.match(ref)):
                err.append(f'{tag}: turn의 ref({ref or "빈칸"})가 카드 id나 조문 위치가 아니다')
            if ref.split('#')[0] in hcases:
                err.append(f'{tag}: turn이 맞히기 구간 판결({ref})을 가리킨다')
        for n in c.get('same_rule') or []:
            if not NO.match(n):
                warn.append(f'{tag}: same_rule 번호 꼴이 이상하다({n})')
            if n in hcases:
                err.append(f'{tag}: same_rule에 맞히기 구간 판결({n})이 있다')
        for h in (c.get('asked') or []) + [x for rp in c.get('rule_parts') or [] for x in rp.get('asked') or []]:
            if h.get('exam') not in EXAMS:
                err.append(f'{tag}: asked의 시험({h.get("exam")})이 공식 기출 코드가 아니다')
            if (h.get('exam'), int(h.get('year') or 0)) in holdout:
                err.append(f'{tag}: asked에 맞히기 구간 출제({h.get("exam")}{h.get("year")})가 있다')
        if no in hcases:
            err.append(f'{tag}: 카드 판결 자체가 맞히기 구간 판결이다')
        sl = c.get('slot')
        if sl:
            fr = frames.get(sl.get('frame'))
            if not fr:
                err.append(f'{tag}: slot의 틀({sl.get("frame")})이 없다')
            elif sl.get('node') not in {n.get('id') for n in fr.get('nodes', [])}:
                err.append(f'{tag}: slot의 마디({sl.get("node")})가 틀에 없다')
        if c.get('confidence') == '확실':
            by = {x.get('by') for x in c.get('checks') or [] if x.get('result') == '확실'}
            if not {'이솝', '파핀'} <= by:
                err.append(f'{tag}: 확실인데 이솝·파핀 둘의 확실 검사가 없다')
            if not (c.get('status') or {}).get('reverse_checked'):
                err.append(f'{tag}: 확실인데 역방향 점검일(status.reverse_checked)이 없다')
            if not quotes_ok:
                err.append(f'{tag}: 확실인데 quote가 다 맞지 않는다')
        ed = c.get('editions') or {}
        if ed.get('court') and (ed.get('court_extra') or ed.get('doctrine')):
            err.append(f'{tag}: 법원판에는 학설·추가 견해 칸을 두지 않는다')

    for fid, f in frames.items():
        for n in f.get('nodes', []):
            basis = n.get('basis') or []
            if not basis:
                err.append(f'틀 {fid}: 마디 {n.get("id")}에 근거가 없다')
            for b in basis:
                if not (b in cards or ART.match(b)):
                    err.append(f'틀 {fid}: 마디 {n.get("id")}의 근거({b})가 카드 id나 조문 위치가 아니다')

    for w in warn:
        print('경고:', w)
    for e in err:
        print('오류:', e)
    print(f'카드 {len(cards)}, 틀 {len(frames)}, 오류 {len(err)}, 경고 {len(warn)}')
    sys.exit(1 if err else 0)


if __name__ == '__main__':
    main()
