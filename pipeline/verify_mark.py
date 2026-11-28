#!/usr/bin/env python3
"""판례 카드에 '검증됨' 표시를 단다(검증틀 v3.2 4단계, 26.11.28).

표시 꼴: card["verified"] = {"date", "guide", "hash", "open": [...]}.
- hash는 카드 글(checks·confidence·verified 칸 뺌) + 판결 원문 body + 그 카드가 slot을 단 틀 마디(문장·근거)를 묶어 잡는다.
  셋 가운데 하나라도 바뀌면 hash가 달라져 표시가 무효가 된다(precedent_check.py가 경고).
- open은 검증하지 못하고 남은 자리다(예: same_rule 상대 판결 원문이 저장소에 없음).

사용:
  python3 -I pipeline/verify_mark.py --check          표시가 있는 카드의 hash가 지금과 같은지만 본다
  python3 -I pipeline/verify_mark.py --mark ID...     카드에 표시를 단다(전수 검증·재검증을 통과한 카드만)
  python3 -I pipeline/verify_mark.py --mark-all       모든 카드에 단다(가이가 검증 완료를 확인한 뒤에만)
"""
import argparse, datetime, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = 'v3.2'
NO = re.compile(r'^(\d{2,4}[가-힣]{1,3}\d+)')


def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def frames():
    out = {}
    for f in (ROOT / 'data' / 'frames').glob('*.json'):
        fr = load(f)
        out[fr['id']] = {n['id']: n for n in fr.get('nodes', [])}
    return out


def card_hash(c, fr):
    body = {k: v for k, v in c.items() if k not in ('checks', 'confidence', 'verified')}
    src = ROOT / 'sources' / 'api' / 'prec' / f"{c['case']['no']}.json"
    sbody = load(src).get('body', '') if src.exists() else ''
    nodes = []
    for s in c.get('slots') or []:
        n = fr.get(s.get('frame'), {}).get(s.get('node'))
        if n:
            nodes.append({'frame': s['frame'], 'node': s['node'], 'element': n.get('element'), 'basis': n.get('basis')})
    blob = json.dumps({'card': body, 'source': hashlib.sha256(sbody.encode('utf-8')).hexdigest(), 'nodes': nodes},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]


def open_items(c):
    out = []
    for n in c.get('same_rule') or []:
        m = NO.match(n)
        if m and not (ROOT / 'sources' / 'api' / 'prec' / f'{m.group(1)}.json').exists():
            out.append(f'same_rule {n}: 원문 없음')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--mark', nargs='*')
    ap.add_argument('--mark-all', action='store_true')
    a = ap.parse_args()
    fr = frames()
    files = sorted((ROOT / 'data' / 'precedents').glob('*.json'))
    want = None if a.mark_all else set(a.mark or [])
    marked = stale = ok = 0
    for f in files:
        c = load(f)
        h = card_hash(c, fr)
        v = c.get('verified')
        if a.check or (not a.mark_all and not a.mark):
            if v:
                if v.get('hash') == h:
                    ok += 1
                else:
                    stale += 1
                    print(f"무효: {c['id']} (카드·원문·틀이 표시 뒤에 바뀜)")
            continue
        if want is not None and c['id'] not in want:
            continue
        c['verified'] = {'date': datetime.date.today().isoformat(), 'guide': GUIDE, 'hash': h, 'open': open_items(c)}
        f.write_text(json.dumps(c, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        marked += 1
    if a.check or (not a.mark_all and not a.mark):
        print(f'검증됨 표시: 유효 {ok}, 무효 {stale}')
        sys.exit(1 if stale else 0)
    print(f'표시를 단 카드 {marked}')


if __name__ == '__main__':
    main()
