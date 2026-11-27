#!/usr/bin/env python3
"""검사기 시험 묶음을 만든다: 진짜 카드를 복사해 한 군데씩 일부러 틀리게 고친 사본(cards/*.json)과 기대 결과.

사용: python3 -I pipeline/tests/verify/make_fixtures.py
- 검사마다 조리법이 하나 넘게 있다. 조리법은 카드를 이름순으로 훑어, 틀린 사본에서는 기대한 검사가 걸리고 고친 사본에서는
  걸리지 않는 첫 카드를 바탕으로 고른다. 그래서 만들어진 사본은 그 시점의 진짜 카드·틀·원장·세트에 기대어 있다.
- 사본은 통째 복사라 진짜 카드를 고쳐도 시험은 그대로다. 다만 다른 카드나 틀에 기대는 시험(turn, same_rule, 틀 basis 등)은
  그쪽이 바뀌면 실패할 수 있다. 그때 이 도구를 다시 돌려 사본을 새로 만든다. 같은 이름의 사본은 덮어쓰고, 이름이 바뀌어
  남은 옛 사본은 지우지 않고 알려 준다(휴지통으로 옮긴다).
- 돌리는 법: python3 -I pipeline/verify_machine.py --selftest
"""
import argparse, copy, importlib.util, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
spec = importlib.util.spec_from_file_location('verify_machine', ROOT / 'pipeline' / 'verify_machine.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

GONE = '__지움__'
FAKE_NO = '2099다99999'
DEAD_BY = '2023다240299#1'


def args():
    return argparse.Namespace(cards=str(ROOT / 'data/precedents'), frames=str(ROOT / 'data/frames'), prec=str(ROOT / 'sources/api/prec'),
                              laws=str(ROOT / 'sources/api/laws'), ledger=str(ROOT / 'data/ledger/ledger-v1.json'), sets=str(ROOT / 'data/sets'),
                              cache=None, no_cache=True, date='2026-11-28')


RECIPES = []


def recipe(name, what):
    def deco(fn):
        RECIPES.append((name, what, fn))
        return fn
    return deco


def E(check, result='후보', **kw):
    return {'check': check, 'result': result, **kw}


def out(m, control, expect, **kw):
    return {'card': m, 'control': control, 'expect': expect, **kw}


@recipe('case-선고일', '선고일을 다른 날로 바꿨다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['case']['date'] = '1999-01-01'
    return out(m, {'case': c['case']}, [E('case 칸', '틀림')])


@recipe('주문-일부를 붙임', "주문에 상고 기각·각하가 없는데 '일부 파기환송'으로 적었다")
def _(c, s, ctx):
    if s.columns[2] != '파기환송' or s.flags['broken'] != '부분':
        return None
    m = copy.deepcopy(c)
    m['case']['disposition'] = '일부 파기환송'
    return out(m, {'case': {**c['case'], 'disposition': '파기환송'}}, [E('주문', '틀림')])


@recipe('주문-각하를 빠뜨림', "일부 상고각하·나머지 상고기각 주문을 '상고기각'으로 적었다(2013다55300#1에서 실제로 있던 어긋남)")
def _(c, s, ctx):
    if s.columns[0] != '상고각하·상고기각':
        return None
    m = copy.deepcopy(c)
    m['case']['disposition'] = '상고기각'
    return out(m, {'case': {**c['case'], 'disposition': s.columns[2]}}, [E('주문', '틀림')])


@recipe('result-방향', '상고기각 판결인데 result에 원심을 파기했다고 적었다')
def _(c, s, ctx):
    if s.flags['broken'] != '없음' or c['case']['disposition'] != s.columns[2]:
        return None
    m = copy.deepcopy(c)
    m['result'] = '원심의 판단에 잘못이 있어 원심을 파기하였다.'
    return out(m, {'result': '원심의 판단이 옳아 상고를 기각하였다.'}, [E('result와 주문')])


@recipe('result-한 갈래', "범위 칸이 '일부'인 판결인데 result에 깨진 갈래만 적었다")
def _(c, s, ctx):
    if s.columns[1] != '일부' or s.flags['broken'] == '없음':
        return None
    m = copy.deepcopy(c)
    m['result'] = '시효가 완성되지 않았다고 본 원심을 파기하였다.'
    return out(m, {'result': '시효가 완성되지 않았다고 본 원심 부분을 파기하고, 나머지 상고는 기각하여 그 부분 원심을 유지하였다.'},
               [E("result와 주문('일부'의 두 갈래)")])


@recipe('slot-주문', "상고기각 판결인데 slot 상태를 '다시 심리(파기환송)'로 적었다")
def _(c, s, ctx):
    if s.flags['broken'] != '없음' or not c.get('slots') or c['slots'][0]['status'] == '다시 심리(파기환송)':
        return None
    m = copy.deepcopy(c)
    m['slots'][0]['status'] = '다시 심리(파기환송)'
    return out(m, {'slots': c['slots']}, [E('slot과 주문', '틀림', claim='slots[0]')])


@recipe('요지 번호', '요지 번호를 같은 판결의 다른 번호로 바꿨다(quote는 원래 요지의 것)')
def _(c, s, ctx):
    keys = [k for k in s.yo if k != str(c['holding'])]
    if not keys:
        return None
    m = copy.deepcopy(c)
    m['holding'] = keys[0]
    return out(m, {'holding': c['holding']}, [E('요지 번호')])


@recipe('한정어-빠짐', '판결요지와 quote에 있는 한정어를 rule에서 지웠다')
def _(c, s, ctx):
    yo = s.yo.get(str(c['holding']))
    qall = ' '.join(rp['quote'] for rp in c['rule_parts'])
    if not yo:
        return None
    for name, pat in vm.QUALS[:3]:
        if name in vm.quals(yo) and name in vm.quals(qall) and name in vm.quals(c['rule']):
            rule = re.sub(r'\s+', ' ', re.sub(pat, '', c['rule']))
            if name not in vm.quals(rule):
                m = copy.deepcopy(c)
                m['rule'] = rule
                return out(m, {'rule': c['rule']}, [E('한정어(요지에만)', basis=name), E('한정어(quote에만)', basis=name)])
    return None


@recipe('한정어-더함', "판결요지와 quote에 없는 '원칙적으로'를 rule에 넣었다")
def _(c, s, ctx):
    yo = s.yo.get(str(c['holding']))
    qall = ' '.join(rp['quote'] for rp in c['rule_parts'])
    if not yo or '원칙적으로' in vm.quals(yo) | vm.quals(qall) | vm.quals(c['rule']):
        return None
    m = copy.deepcopy(c)
    m['rule'] = '원칙적으로 ' + c['rule']
    return out(m, {'rule': c['rule']}, [E('한정어(rule에만)', basis='원칙적으로'), E('한정어(rule에만, quote 대조)', basis='원칙적으로')])


@recipe('낱말 차집합', '판결에 없는 낱말(다른 제도)이 든 사실 줄을 더했다')
def _(c, s, ctx):
    w = next((w for w in ('유치권', '선의취득', '공탁금') if w not in s.bsq), None)
    if not w:
        return None
    m = copy.deepcopy(c)
    m['facts'] = c['facts'] + [f'피고는 그 뒤 {w}을 주장하였다.']
    return out(m, {'facts': c['facts']}, [E('낱말 차집합', claim=f"facts[{len(c['facts'])}]", basis=w)])


@recipe('날짜·금액', '판결에 없는 날짜와 금액이 든 사실 줄을 더했다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['facts'] = c['facts'] + ['피고는 2031. 2. 3. 원고에게 7,777만 원을 지급하였다.']
    return out(m, {'facts': c['facts']}, [E('날짜·금액', claim=f"facts[{len(c['facts'])}]", basis='2031. 2. 3.')])


@recipe('원심 문단', "quote를 '원심은…'으로 시작하는 문장에서 땄다")
def _(c, s, ctx):
    for mm in re.finditer(r'(?:^|\n|다\. )(원심은 [^.\n]{60,300}다)\.', s.body[s.reason_start:s.maj_end]):
        q = mm.group(1)[4:74].strip()
        if s.find(q) >= 0 and '원심' not in q:
            m = copy.deepcopy(c)
            m['rule_parts'][0]['quote'] = q
            return out(m, {'rule_parts': c['rule_parts']}, [E('원심 문단 표시', claim='rule_parts[0]', basis="'원심은…'으로 시작")])
    return None


@recipe('quote 자리', 'quote를 본문에 없는 글로 바꿨다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['rule_parts'][0]['quote'] = '이 구절은 판결 본문 어디에도 없는 글이다'
    return out(m, {'rule_parts': c['rule_parts']}, [E('quote 자리', '틀림', claim='rule_parts[0]')])


@recipe('참조조문', '이 판결의 참조조문에 없는 조문을 articles에 더했다')
def _(c, s, ctx):
    if not s.refs_articles or '999' in s.refs_articles:
        return None
    m = copy.deepcopy(c)
    m['articles'] = c['articles'] + [{'law': '민법', 'jo': '999', 'para': None, 'role': '보조'}]
    return out(m, {'articles': c['articles']}, [E('참조조문', claim=f"articles[{len(c['articles'])}].role")])


@recipe('따옴표', '판결에 없는 말을 따옴표로 cue에 넣었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['cue'] = c['cue'] + ' 피고는 "전혀 없는 말을 지어내 적었다"고 다투었다.'
    return out(m, {'cue': c['cue']}, [E('따옴표', basis='전혀 없는 말')])


@recipe('글 속 사건번호', '저장소에 원문이 없는 사건번호를 not_decided에 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['not_decided'] = ((c.get('not_decided') or '') + ' 뒤 판결 2099다12345도 같은 취지다.').strip()
    return out(m, {'not_decided': c.get('not_decided')}, [E('글 속 사건번호 원문', '틀림', basis='2099다12345')])


@recipe('same_rule 원문', '저장소에 원문이 없는 사건번호를 same_rule에 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['same_rule'] = c['same_rule'] + ['2099다12345']
    return out(m, {'same_rule': c['same_rule']}, [E('same_rule 원문', '틀림', claim=f"same_rule[{len(c['same_rule'])}]")])


@recipe('괄호 속 인용', "이 판결이 들지 않은 판결을 '이 판결이 든'이라고 괄호에 적었다")
def _(c, s, ctx):
    x = next((n for n in sorted(ctx.srcs) if n != s.no and n not in s.body and n not in s.refs_cases), None)
    m = copy.deepcopy(c)
    m['result'] = c['result'] + f' (이 판결이 든 {x} 참조)'
    return out(m, {'result': c['result']}, [E('괄호 속 사건번호 인용', basis=x)])


@recipe('글 속 카드 id', '없는 카드 id를 not_decided에 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['not_decided'] = ((c.get('not_decided') or '') + ' 이 부분은 2099다12345#2 카드가 맡는다.').strip()
    return out(m, {'not_decided': c.get('not_decided')}, [E('글 속 카드 id', '틀림', basis='2099다12345#2')])


def dead_card(ctx):
    return next(o for o in ctx.cards.values() if (o.get('status') or {}).get('current') is False)


@recipe('turn ref 현행', 'turn의 ref를 current false 카드로 두었다')
def _(c, s, ctx):
    d = dead_card(ctx)
    if d['case']['no'] == s.no:
        return None
    m = copy.deepcopy(c)
    m['turn'] = c['turn'] + [{'fact': '시험용 사실이다.', 'result': '시험용 결론이다.', 'ref': d['id']}]
    return out(m, {'turn': c['turn']}, [E('turn ref 현행', claim=f"turn[{len(c['turn'])}]")])


@recipe('turn 같은 상태', 'turn의 ref를 같은 마디에서 상태가 같은 카드로 두었다(결론이 같다)')
def _(c, s, ctx):
    mine = vm.slot_map(c)
    for o in ctx.cards.values():
        theirs = vm.slot_map(o)
        sh = set(mine) & set(theirs)
        if o['case']['no'] != s.no and sh and all(mine[k] == theirs[k] for k in sh) and (o.get('status') or {}).get('current') is not False:
            m = copy.deepcopy(c)
            m['turn'] = c['turn'] + [{'fact': '시험용 사실이다.', 'result': '시험용 결론이다.', 'ref': o['id']}]
            return out(m, {'turn': c['turn']}, [E('같은 마디·같은 상태 turn', claim=f"turn[{len(c['turn'])}]")])
    return None


@recipe('같은 판결 turn', 'turn의 ref를 같은 판결의 다른 요지 카드로 두었다')
def _(c, s, ctx):
    sib = [o for o in ctx.by_case[s.no] if o['id'] != c['id']]
    if not sib:
        return None
    m = copy.deepcopy(c)
    m['turn'] = c['turn'] + [{'fact': '시험용 사실이다.', 'result': '시험용 결론이다.', 'ref': sib[0]['id']}]
    return out(m, {'turn': c['turn']}, [E('같은 판결 turn', claim=f"turn[{len(c['turn'])}]")])


@recipe('turn 이웃 쟁점', "turn의 result를 '…가 문제 된다'로 적었다")
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['turn'] = c['turn'] + [{'fact': '공사가 끝난 날이 다르다.', 'result': '공사대금채권의 기산점이 문제 된다.', 'ref': '민법 제166조 제1항'}]
    return out(m, {'turn': c['turn']}, [E('turn 이웃 쟁점', claim=f"turn[{len(c['turn'])}]")])


@recipe('same_rule 변경 표기', '판례가 바뀐 판결을 same_rule에 적었다')
def _(c, s, ctx):
    d = dead_card(ctx)
    if d['case']['no'] == s.no or d['case']['no'] in c['same_rule']:
        return None
    m = copy.deepcopy(c)
    m['same_rule'] = c['same_rule'] + [d['case']['no']]
    return out(m, {'same_rule': c['same_rule']}, [E('same_rule 변경 표기', claim=f"same_rule[{len(c['same_rule'])}]")])


@recipe('same_rule 방향', '같은 마디에서 상태가 반대인 판결을 same_rule에 적었다')
def _(c, s, ctx):
    mine = vm.slot_map(c)
    for o in ctx.cards.values():
        theirs = vm.slot_map(o)
        if o['case']['no'] != s.no and o['case']['no'] not in c['same_rule'] and any({mine[k], theirs[k]} == {'인정', '배척'} for k in set(mine) & set(theirs)):
            m = copy.deepcopy(c)
            m['same_rule'] = c['same_rule'] + [o['case']['no']]
            return out(m, {'same_rule': c['same_rule']}, [E('same_rule 방향', claim=f"same_rule[{len(c['same_rule'])}]")])
    return None


@recipe('same_rule과 turn 겹침', 'turn이 가리키는 판결을 same_rule에도 적었다')
def _(c, s, ctx):
    refs = [t['ref'].split('#')[0] for t in c['turn'] if t['ref'] in ctx.cards and t['ref'].split('#')[0] not in c['same_rule'] and t['ref'].split('#')[0] != s.no]
    if not refs:
        return None
    m = copy.deepcopy(c)
    m['same_rule'] = c['same_rule'] + [refs[0]]
    return out(m, {'same_rule': c['same_rule']}, [E('same_rule과 turn 겹침', claim=f"same_rule[{len(c['same_rule'])}]")])


@recipe('asked와 원장', '원장에 없는 설문을 asked에 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['asked'] = c['asked'] + [{'exam': '변', 'subject': '민사법', 'year': 2031, 'q': '9', 'sub': '9', 'similarity': '중', 'diff': '결론 같음. 시험용 줄이다.'}]
    return out(m, {'asked': c['asked']}, [E('asked와 원장', claim=f"asked[{len(c['asked'])}]")])


@recipe('asked 거꾸로', '세트 글에 이 판결이 나오는 설문을 asked에서 지웠다')
def _(c, s, ctx):
    for h in c['asked']:
        key = (h['exam'], int(h['year']), str(h['q']), str(h.get('sub') or ''))
        hit = [x for x in ctx.set_cites.get(s.no, ()) if (x[0], x[1], x[3], x[4]) == key]
        if hit and len(ctx.by_case[s.no]) == 1:
            m = copy.deepcopy(c)
            m['asked'] = [x for x in c['asked'] if x is not h]
            for rp in m['rule_parts']:
                rp['asked'] = []
            return out(m, {'asked': c['asked'], 'rule_parts': c['rule_parts']},
                       [E('asked 거꾸로', claim=f'판결/{s.no}', basis=f'세트 {hit[0][0]}{hit[0][1]}-{hit[0][2]}-{hit[0][3]} 설문 {hit[0][4]}')])
    return None


@recipe('세트 basis와 등급', '카드 유사도를 세트 basis의 등급보다 낮게 적었다')
def _(c, s, ctx):
    for i, h in enumerate(c['asked']):
        sb = ctx.set_basis.get((h['exam'], int(h['year']), str(h['q']), str(h.get('sub') or ''), s.no))
        if sb and sb[0] in ('상', '중') and h['similarity'] == sb[0]:
            m = copy.deepcopy(c)
            m['asked'][i]['similarity'] = '하'
            return out(m, {'asked': c['asked']}, [E('세트 basis와 등급', claim=f'asked[{i}].similarity')])
    return None


@recipe('diff 첫머리', "diff가 '결론 같음/반대'로 시작하지 않는다")
def _(c, s, ctx):
    if not c['asked'] or re.match(r'^\s*결론 (같음|반대)', c['asked'][0]['diff'] or ''):
        return None
    fixed = copy.deepcopy(c['asked'])
    for h in fixed:
        h['diff'] = '결론 같음. ' + (h['diff'] or '')
    return out(copy.deepcopy(c), {'asked': fixed}, [E('diff 첫머리', claim='asked[0].diff')])


@recipe('공보-다름', '공보 표기를 다른 판결들이 적는 것과 다르게 적었다')
def _(c, s, ctx):
    if not c['case'].get('gazette') or re.sub(r'[\s,]', '', c['case']['gazette']) not in (ctx.gazette.get(s.no) or {}):
        return None
    m = copy.deepcopy(c)
    m['case']['gazette'] = '공1900상, 1'
    return out(m, {'case': c['case']}, [E('공보', basis='다르다')])


@recipe('공보-비움', '다른 판결 두 곳이 같은 표기로 적는 공보를 비워 두었다')
def _(c, s, ctx):
    got = ctx.gazette.get(s.no) or {}
    k = re.sub(r'[\s,]', '', c['case'].get('gazette') or '')
    if not k or len(got) != 1 or len(got.get(k, ())) < 2:
        return None
    m = copy.deepcopy(c)
    m['case']['gazette'] = None
    return out(m, {'case': c['case']}, [E('공보', basis='채울 후보')])


@recipe('bar_extra', '반대의견이 없는 판결에 kind 반대의견을 적었다')
def _(c, s, ctx):
    if s.opinions or c['editions'].get('bar_extra'):
        return None
    m = copy.deepcopy(c)
    m['editions']['bar_extra'] = {'kind': '반대의견', 'text': '시효는 이미 완성되었다고 보아야 한다(대법관 홍길동).'}
    return out(m, {'editions': c['editions']}, [E('bar_extra와 구역표', claim='bar_extra.kind')])


@recipe('bar_extra-이름', '반대의견을 낸 대법관 이름을 틀리게 적었다')
def _(c, s, ctx):
    zs = [o for o in s.opinions if o['kind'] == '반대의견']
    bx = c['editions'].get('bar_extra')
    if not zs or not bx or bx['kind'] != '반대의견':
        return None
    m = copy.deepcopy(c)
    m['editions']['bar_extra'] = {'kind': '반대의견', 'text': '시효는 이미 완성되었다고 보아야 한다(대법관 홍길동, 임꺽정).'}
    return out(m, {'editions': c['editions']}, [E('bar_extra와 구역표', claim='bar_extra.s0', basis='홍길동')])


@recipe('일관성-일부 변경', '일부만 바뀐 판결(scope에 범위 밖이라고 적음)을 current false로 두었다')
def _(c, s, ctx):
    st = c['status']
    if st.get('current') is not True or not re.search(r'범위 밖', st.get('scope') or ''):
        return None
    m = copy.deepcopy(c)
    m['status'] = {**st, 'current': False, 'overruled_by': DEAD_BY}
    return out(m, {'status': st}, [E('일관성(일부 변경)', claim='status.current')])


@recipe('일관성-같은 판결', '같은 판결의 다른 요지 카드에는 변경 표시가 있는데 이 카드의 scope를 비웠다')
def _(c, s, ctx):
    st = c['status']
    sib = [o for o in ctx.by_case[s.no] if o['id'] != c['id'] and (o['status'].get('scope') or o['status'].get('current') is False)]
    if not sib or not st.get('scope') or st.get('current') is False:
        return None
    m = copy.deepcopy(c)
    m['status'] = {k: v for k, v in st.items() if k != 'scope'}
    return out(m, {'status': st}, [E('일관성(같은 판결 다른 요지)', claim='scope')])


@recipe('틀 basis 현행', '틀 마디의 근거인 카드를 current false로 두었다')
def _(c, s, ctx):
    if c['status'].get('current') is not True or not any(c['id'] in bs for bs in ctx.basis.values()):
        return None
    m = copy.deepcopy(c)
    m['status'] = {**c['status'], 'current': False, 'overruled_by': DEAD_BY, 'scope': '이 요지 전부가 변경되었다.'}
    return out(m, {'status': c['status']}, [E('틀 basis 현행', claim='status.current')])


@recipe('참조판례 변경 경고', '어느 판결이 참조판례로 든 판결의 카드를 current false로 두었다(결과는 든 쪽 카드에 나온다)')
def _(c, s, ctx):
    if c['status'].get('current') is not True or len(ctx.by_case[s.no]) != 1:
        return None
    for x in ctx.cards.values():
        xs = ctx.srcs.get(x['case']['no'])
        if xs and x['case']['no'] != s.no and s.no in vm.NO.findall(xs.refs_cases):
            m = copy.deepcopy(c)
            m['status'] = {**c['status'], 'current': False, 'overruled_by': DEAD_BY, 'scope': '이 요지 전부가 변경되었다.'}
            return out(m, {'status': c['status']}, [E('참조판례 변경 경고', basis=c['id'])], watch=x['id'])
    return None


@recipe('slot과 틀 basis', '그 마디 basis에 이 카드가 없는 틀 마디에 slot을 달았다')
def _(c, s, ctx):
    k = next(k for k, bs in ctx.basis.items() if c['id'] not in bs and k not in vm.slot_map(c))
    m = copy.deepcopy(c)
    m['slots'] = c['slots'] + [{'frame': k[0], 'node': k[1], 'status': '인정'}]
    return out(m, {'slots': c['slots']}, [E('slot과 틀 basis', '틀림', claim=f"slots[{len(c['slots'])}]")])


@recipe('틀 basis에만 있음', '틀 마디 basis에 있는 카드에서 그 마디 slot을 지웠다')
def _(c, s, ctx):
    for i, sl in enumerate(c['slots']):
        if c['id'] in ctx.basis.get((sl['frame'], sl['node']), ()):
            m = copy.deepcopy(c)
            del m['slots'][i]
            return out(m, {'slots': c['slots']}, [E('틀 basis에만 있음', basis=f"{sl['frame']}/{sl['node']}")])
    return None


@recipe('덮음-모르는 칸', '주장 표에 없는 칸을 카드에 더했다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['memo'] = '시험용 칸이다.'
    return out(m, {'memo': GONE}, [E('덮음', claim='memo')])


@recipe('덮음-마디 없는 문장', '어느 마디도 받치지 않는 문장을 rule에 더했다')
def _(c, s, ctx):
    n = len(vm.split_sents(c['rule']))
    m = copy.deepcopy(c)
    m['rule'] = c['rule'] + ' 유치권자는 경매를 신청할 수 있으나 매각대금에서 우선변제를 받지는 못한다.'
    return out(m, {'rule': c['rule']}, [E('덮음', claim=f'rule.s{n}')])


@recipe('cue 쟁점 문장', 'cue를 사실 없이 쟁점 문장으로만 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['cue'] = '소멸시효가 완성되었는지가 문제다.'
    return out(m, {'cue': c['cue']}, [E('cue 쟁점 문장')])


@recipe('작업 기록 낱말', '검토자 이름과 확인 경위를 not_decided에 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['not_decided'] = ((c.get('not_decided') or '') + ' 파핀이 원문을 읽고 확인하였다.').strip()
    return out(m, {'not_decided': c.get('not_decided')}, [E('작업 기록 낱말')])


@recipe('rule 속 주석', 'rule 앞에 판례 변경 주석을 붙였다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['rule'] = '(변경된 법리. 지금은 다르게 본다.) ' + c['rule']
    return out(m, {'rule': c['rule']}, [E('rule 속 주석')])


@recipe('닫힌 값', 'found_by에 정해지지 않은 값을 적었다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['found_by'] = '어디선가'
    return out(m, {'found_by': c['found_by']}, [E('닫힌 값', '틀림')])


@recipe("role '최근' 기한", "오래된 판결에 role '최근'을 달았다")
def _(c, s, ctx):
    if c['case']['date'] > '2010' or c['role'] == '최근':
        return None
    m = copy.deepcopy(c)
    m['role'] = '최근'
    return out(m, {'role': c['role']}, [E("role '최근' 기한")])


@recipe('잘린 단서', "quote를 바로 뒤에 '다만'이 이어지는 문장에서 따고 rule에는 단서를 적지 않았다")
def _(c, s, ctx):
    for mm in re.finditer(r'([^.\n]{60,300}다)\. 다만[^.\n]{10,}', s.body[s.reason_start:s.maj_end]):
        q = mm.group(1)[-60:].strip()
        if s.find(q) >= 0 and s.body.count(q[-12:]) == 1:
            m = copy.deepcopy(c)
            m['rule'] = '시험용 법리 문장이다.'
            m['rule_parts'] = [{'part': '시험용 마디', 'quote': q, 'asked': []}]
            return out(m, {'rule': c['rule'], 'rule_parts': c['rule_parts']}, [E('잘린 단서', claim='omit')])
    return None


@recipe('결론 대목의 날짜', '대법원의 결론 문장에 나오는 날짜를 facts·cue·result에서 모두 지웠다')
def _(c, s, ctx):
    m = copy.deepcopy(c)
    m['facts'] = [vm.DATE.sub('그날 ', f) for f in c['facts']]
    m['cue'] = vm.DATE.sub('그날 ', c['cue'])
    m['result'] = vm.DATE.sub('그날 ', c['result'])
    if m['facts'] == c['facts'] and m['cue'] == c['cue'] and m['result'] == c['result']:
        return None
    return out(m, {'facts': c['facts'], 'cue': c['cue'], 'result': c['result']}, [E('결론 대목의 날짜', claim='omit')])


@recipe('not_decided 안내', '카드가 있는 요지를 카드로 만들지 않았다고 적었다')
def _(c, s, ctx):
    sib = [o for o in ctx.by_case[s.no] if o['id'] != c['id'] and str(o['holding']).isdigit()]
    if not sib:
        return None
    m = copy.deepcopy(c)
    m['not_decided'] = ((c.get('not_decided') or '') + f" 요지 {sib[0]['holding']}는 카드로 만들지 않았다.").strip()
    return out(m, {'not_decided': c.get('not_decided')}, [E('not_decided 안내')])


def fake_source(body_line, redacted=False):
    rec = {'no': FAKE_NO, 'serial': '0', 'court': '대법원', 'date': '20990101', 'kind': '판결', 'name': '대여금', 'refs_articles': '', 'refs_cases': '',
           'fetched': '2026-11-28', 'source': '시험용으로 지은 글(판결이 아니다)',
           'body': '【원고, 상고인】 원고\n【피고, 피상고인】 피고\n【원심판결】 시험고법 2098. 1. 1. 선고 2097나1 판결\n【주 문】\n상고를 기각한다. 상고비용은 원고가 부담한다.\n\n'
                   '【이 유】 1. ' + body_line + '\n2. 그러므로 상고를 기각한다.\n대법관 갑(재판장) 을 병'}
    if redacted:
        rec['redacted'] = ['시험용 가림 기록']
    return rec


def fake_card():
    return {'id': FAKE_NO + '#1', 'role': '바탕', 'case': {'no': FAKE_NO, 'court': '대법원', 'date': '2099-01-01', 'kind': '판결', 'en_banc': False, 'gazette': None, 'disposition': '상고기각'},
            'holding': '1', 'found_by': '검색', 'searched': ['시험'], 'name': None, 'cue': '원고가 돈을 빌려주었다.', 'facts': ['원고가 돈을 빌려주었다.'], 'rule': '상고를 기각한다.',
            'rule_parts': [{'part': '상고를 기각한다', 'quote': '그러므로 상고를 기각한다', 'asked': []}], 'result': '상고를 기각하였다.', 'turn': [], 'not_decided': None, 'slots': [],
            'articles': [], 'same_rule': [], 'asked': [], 'status': {'current': True, 'overruled_by': None, 'reverse_checked': '2026-11-28'},
            'editions': {'court': True, 'bar': True, 'bar_extra': None}, 'confidence': '확인 필요', 'checks': []}


SPECIAL = [
    ('이름 후보', '판결 본문에 가려지지 않은 개인 이름(역할 낱말 뒤의 성+이름)이 있다. 시험용으로 지은 판결 글과 지어낸 이름이다',
     lambda: out(fake_card(), {}, [E('이름 후보', claim=f'판결/{FAKE_NO}')], source=fake_source('원고는 소외 홍길동에게 돈을 빌려주었다. 소외 홍길동은 이를 갚지 않았다.'),
                 control_source=fake_source('원고는 소외 1에게 돈을 빌려주었다. 소외 1은 이를 갚지 않았다.'))),
    ('가림 표지', '우리가 가린 이름 두 사람이 같은 표지(○○○)다. 시험용으로 지은 판결 글이다',
     lambda: out(fake_card(), {}, [E('가림 표지', claim=f'판결/{FAKE_NO}')], source=fake_source('원고는 소외 ○○○에게 돈을 빌려주었다. 소외 ○○○이 보증하였다.', True),
                 control_source=fake_source('원고는 소외 ○○○1에게 돈을 빌려주었다. 소외 ○○○2가 보증하였다.', True))),
]

# precedent_check.py의 검사. 카드마다 다른 바탕 카드를 쓴다(임시 폴더에 한꺼번에 덮어 한 번 돌린다).
PC = [
    ('조문 실재', '현행 원문에 없는 조문을 articles에 적었다', lambda m: m['articles'].append({'law': '민법', 'jo': '9999', 'para': None, 'role': '보조'}), ['민법 제9999조가 현행 원문에 없다']),
    ('조문 항', '그 조에 없는 항을 articles에 적었다', lambda m: m['articles'].append({'law': '민법', 'jo': '162', 'para': '9', 'role': '보조'}), ['민법 제162조에 제9항이 없다']),
    ('quote', 'quote를 본문에 없는 글로 바꿨다', lambda m: m['rule_parts'][0].__setitem__('quote', '이 구절은 판결 본문 어디에도 없는 글이다'), ['rule_parts[0] quote가 판결 본문에 없다', '확실인데 quote가 다 맞지 않는다']),
    ('asked subject', 'asked에서 과목을 뺐다', lambda m: m['asked'][0].pop('subject'), ['asked에 subject가 없다']),
    ('asked 시험 코드', 'asked에 공식 기출이 아닌 시험 코드를 적었다', lambda m: m['asked'][0].__setitem__('exam', '모'), ['공식 기출 코드가 아니다']),
    ('마디 asked', '카드 asked에 없는 설문을 마디 asked에 적었다',
     lambda m: m['rule_parts'][0]['asked'].append({'exam': '변', 'subject': '민사법', 'year': 2031, 'q': '9', 'sub': '9'}), ['가 카드 asked에 없다']),
    ('turn ref', 'turn의 ref를 카드 id도 조문 위치도 아닌 글로 적었다', lambda m: m['turn'].append({'fact': '시험', 'result': '시험', 'ref': '어느 판결'}), ['turn의 ref(어느 판결)가 카드 id나 조문 위치가 아니다']),
    ('slot 틀', '없는 틀에 slot을 달았다', lambda m: m['slots'].append({'frame': 'F-없는틀', 'node': '항변-1', 'status': '인정'}), ['slot의 틀(F-없는틀)이 없다']),
    ('slot 마디', '틀에 없는 마디에 slot을 달았다', lambda m: m['slots'].append({'frame': 'F-소멸시효항변', 'node': '없는마디-9', 'status': '인정'}), ['slot의 마디(없는마디-9)가 틀에 없다']),
    ('role', 'role에 정해지지 않은 값을 적었다', lambda m: m.__setitem__('role', '참고'), ['role은 바탕·구별·최근 가운데 하나다']),
    ('bar_extra kind', 'bar_extra에 학설 줄을 적었다', lambda m: m['editions'].__setitem__('bar_extra', {'kind': '학설', 'text': '반대하는 견해가 있다.'}), ['bar_extra는 kind']),
    ('확실 조건', '확실인데 파핀의 확실 검사를 뺐다', lambda m: m.__setitem__('checks', [x for x in m['checks'] if x.get('by') != '파핀']), ['확실인데 이솝·파핀 둘의 확실 검사가 없다']),
    ('선고일', '선고일을 원문과 다르게 적었다', lambda m: m['case'].__setitem__('date', '1999-01-01'), ['선고일이 원문']),
    ('id와 요지 번호', '요지 번호를 id와 다르게 적었다', lambda m: m.__setitem__('holding', '99'), ['가 사건번호#요지번호']),
    ('current false', 'current false인데 overruled_by를 비웠다', lambda m: m.__setitem__('status', {**m['status'], 'current': False, 'overruled_by': None}), ['current가 false인데 overruled_by가 없다']),
    ('open_turns', '저장소에 두지 않는 open_turns 칸을 넣었다', lambda m: m.__setitem__('open_turns', []), ['open_turns는 저장소에 두지 않는다']),
]


def main():
    a = args()
    ctx = vm.Ctx(a)
    law_text = vm.load_law_text(a)
    outdir = HERE / 'cards'
    outdir.mkdir(exist_ok=True)
    n, fails, written = 0, [], set()

    def good(fx):
        bad = vm.run_overlay(ctx, fx['card'], law_text, fx.get('watch'), fx.get('source'))
        ok = vm.run_overlay(ctx, vm.fixed_copy(fx), law_text, fx.get('watch'), fx.get('control_source') or fx.get('source'))
        return all(vm.expect_hit(bad, e) and not vm.expect_hit(ok, e) for e in fx['expect'])

    def write(name, what, fx, tool='verify_machine'):
        nonlocal n
        n += 1
        doc = {'tool': tool, 'name': name, 'what': what, **{k: v for k, v in fx.items() if k != 'card'}, 'card': fx['card']}
        fn = f"{n:02d}-{re.sub(r'[^0-9A-Za-z가-힣_]+', '-', name).strip('-')}.json"
        written.add(fn)
        (outdir / fn).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    for name, what, fn in RECIPES:
        for c in ctx.cards.values():
            s = ctx.srcs.get(c['case']['no'])
            try:
                fx = fn(c, s, ctx) if s else None
            except (StopIteration, KeyError, IndexError):
                fx = None
            if fx and good(fx):
                write(name, what, fx)
                break
        else:
            fails.append(name)
    for name, what, fn in SPECIAL:
        fx = fn()
        if good(fx):
            write(name, what, fx)
        else:
            fails.append(name)
    used = set()
    for name, what, mut, expect in PC:
        for c in ctx.cards.values():
            if c['id'] in used or c['confidence'] != '확실' or not (c['asked'] and c['slots'] and c['turn'] is not None):
                continue
            m = copy.deepcopy(c)
            try:
                mut(m)
            except (KeyError, IndexError):
                continue
            used.add(c['id'])
            write(name, what, {'card': m, 'file': c['id'].replace('#', '-') + '.json', 'expect': expect}, tool='precedent_check')
            break
        else:
            fails.append(name)
    print(f'시험 카드 {n}장을 {outdir}에 썼다.' + (f' 바탕 카드를 찾지 못한 조리법: {", ".join(fails)}' if fails else ''))
    stale = sorted(p.name for p in outdir.glob('*.json') if p.name not in written)
    if stale:
        print('이번에 만들지 않은 옛 사본이 남아 있다(휴지통으로 옮긴다):', ', '.join(stale))
    sys.exit(1 if fails or stale else 0)


if __name__ == '__main__':
    main()
