#!/usr/bin/env python3
"""판례 카드 검수 페이지: 요건사실 틀마다 마디와 그 자리에 놓인 판례 카드를 한 줄씩 보여 주고 줄마다 댓글을 받는다.

사용: python3 -I pipeline/precedent-review-page.py --out <파일>
Artifact로 올릴 때 capabilities: {comments: {}}. 줄을 누르면 입력칸이 열리고 Enter로 바로 Claude에게 간다(comment-widget.js).
작업 기록(checks의 note)은 싣지 않는다. 사람이 볼 것은 법리·사안·결론·갈림·기출이다.
"""
import html, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
e = html.escape
out = Path(sys.argv[sys.argv.index('--out') + 1])
widget = (ROOT / 'pipeline' / 'comment-widget.js').read_text(encoding='utf-8')
EXAM = {'원': '법원행정고시', '법': '법무사', '변': '변호사시험', '사': '사법시험', '입': '입법고시', '리': '변리사',
        '행': '5급 공채', '노': '노무사', '감': '감정평가사'}
STAGE_ORDER = {'직권조사': 0, '청구원인': 1, '항변': 2, '재항변': 3, '재재항변': 4}

cards = {}
for f in sorted((ROOT / 'data' / 'precedents').glob('*.json')):
    c = json.loads(f.read_text(encoding='utf-8'))
    cards[c['id']] = c
frames = {}
for f in sorted((ROOT / 'data' / 'frames').glob('*.json')):
    fr = json.loads(f.read_text(encoding='utf-8'))
    frames[fr['id']] = fr

# 틀 순서: 1단계(책임재산 보전), 2단계(소멸시효) 틀 먼저, 그다음 0단계 틀
FIRST = ['F-채권자대위소송', 'F-대위-명의신탁-진정명의회복', 'F-대위-이중매매-등기말소', 'F-대위-반사회적처분-등기말소',
         'F-대위-취득시효-소유권이전등기', 'F-사해행위취소소송', 'F-사해행위취소반소', 'F-사해방지참가', 'F-취소후-회복재산-등기말소',
         'F-소멸시효항변', 'F-시효중단재소', 'F-불법행위손해배상-시효항변']
order = [x for x in FIRST if x in frames] + [x for x in frames if x not in FIRST]

def aid(cid):
    return 'c-' + cid.replace('#', '-')

def link(ref):
    if ref in cards:
        return f'<a href="#{e(aid(ref))}">{e(ref)}</a>'
    return e(ref)

def home(c):
    s = c.get('slots') or []
    return s[0]['frame'] if s and s[0]['frame'] in frames else None

by_frame = {k: [] for k in order}
loose = []
for c in cards.values():
    h = home(c)
    (by_frame[h] if h else loose).append(c)

def node_key(c, fid):
    for s in c.get('slots') or []:
        if s['frame'] == fid:
            st, _, n = s['node'].partition('-')
            return (STAGE_ORDER.get(st, 9), int(n) if n.isdigit() else 0, c['id'])
    return (9, 0, c['id'])

CSS = """
/* 검수 장부: 틀 하나가 한 묶음, 카드 한 장이 한 블록, 줄 하나가 댓글 한 자리 */
:root{--paper:#f5f6f8;--sheet:#fff;--ink:#171c26;--muted:#586172;--rule:#d7dbe3;--navy:#24457a;--seal:#b0302a;--soft:#eef1f6;--hi:#fff5df;--hi-line:#bf9640;--ok:#2f6b4a;
--display:"Nanum Myeongjo","AppleMyungjo","Noto Serif KR",serif;--body:"IBM Plex Sans KR","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#11151c;--sheet:#192029;--ink:#e5e9ef;--muted:#9aa3b1;--rule:#2b333f;--navy:#a3bce6;--seal:#f08b82;--soft:#1f2732;--hi:#29231a;--hi-line:#c9a24a;--ok:#8cc9a5;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#11151c;--sheet:#192029;--ink:#e5e9ef;--muted:#9aa3b1;--rule:#2b333f;--navy:#a3bce6;--seal:#f08b82;--soft:#1f2732;--hi:#29231a;--hi-line:#c9a24a;--ok:#8cc9a5;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.6;word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:760px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:26px 64px;display:grid;gap:16px}
h1{font-family:var(--display);font-weight:800;font-size:1.7rem;margin:0;text-wrap:balance}
p{margin:0}.lead{color:var(--muted);max-width:64ch}
a{color:var(--navy)}
h2{font-family:var(--display);font-size:1.25rem;margin:22px 0 0;text-wrap:balance}h2 small{font-family:var(--body);font-size:.78rem;color:var(--muted);font-weight:400;margin-left:6px}
.toc{display:grid;gap:2px;font-size:.9rem}.toc a{text-decoration:none}.toc span{color:var(--muted);font-variant-numeric:tabular-nums}
.look{display:grid;gap:4px;padding-left:1.2em;margin:0;color:var(--ink);font-size:.92rem}
.frame{background:var(--soft);border-radius:12px;padding:12px 14px;display:grid;gap:4px;min-width:0}
.card{background:var(--sheet);border:1px solid var(--rule);border-radius:12px;padding:14px 16px;display:grid;gap:4px;min-width:0;scroll-margin-top:12px}
.head{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:baseline}
.cid{font-family:var(--mono);font-size:.82rem;font-weight:600}
.meta{font-size:.8rem;color:var(--muted)}
.chip{font-size:.72rem;border:1px solid var(--rule);border-radius:999px;padding:0 8px;color:var(--muted);white-space:nowrap}
.chip.role-구별{border-color:var(--hi-line);color:var(--ink)}.chip.role-최근{border-color:var(--navy);color:var(--navy)}
.chip.ok{border-color:var(--ok);color:var(--ok)}.chip.warn{border-color:var(--seal);color:var(--seal)}
.row{display:grid;grid-template-columns:4.4em 1fr;gap:8px;align-items:baseline;padding:2px 4px}
.k{font-size:.74rem;color:var(--navy);font-weight:600}
.v{min-width:0}.v.d{font-family:var(--display)}.v.s{font-size:.9rem;color:var(--muted)}
q{quotes:"“" "”";background:var(--hi);border-bottom:1px solid var(--hi-line)}
.hint{font-size:.86rem;color:var(--navy);background:var(--soft);border-radius:10px;padding:8px 12px}
body.cm-on .ln{cursor:text;border-radius:6px}
@media (hover:hover){body.cm-on .ln:hover{background:var(--soft)}}
.ln.on{background:var(--soft)}.ln.sent{box-shadow:inset 3px 0 0 var(--seal)}
.cbox{display:grid;gap:6px;margin:2px 0 6px;padding:8px;border:1px solid var(--navy);border-radius:10px;background:var(--sheet)}
.cbox textarea{font:inherit;font-size:16px;line-height:1.5;width:100%;box-sizing:border-box;min-height:44px;resize:none;border:1px solid var(--rule);border-radius:8px;padding:8px 10px;background:var(--paper);color:var(--ink)}
.cbox textarea:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.cbox .row{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;justify-content:space-between;grid-template-columns:none}
.cbox .st{font-size:.78rem;color:var(--muted);min-width:0}.cbox .st.ok{color:var(--navy)}.cbox .st.err{color:var(--seal)}
.cbox .go{font:inherit;font-size:.84rem;border:0;border-radius:8px;background:var(--navy);color:var(--sheet);padding:6px 14px;min-height:36px;cursor:pointer}
.cbox .go:disabled{opacity:.5;cursor:default}
"""

def row(id, k, v, cls='v'):
    return f'<div class="row ln" id="{e(id)}"><span class="k">{e(k)}</span><span class="{cls}">{v}</span></div>'

def card_html(c):
    a = aid(c['id'])
    cs = c['case']
    when = cs['date'].replace('-', '. ') + '.'
    kind = cs.get('kind') or '판결'
    head = [f'<span class="cid">{e(c["id"])}</span>',
            f'<span class="chip role-{e(c["role"])}">{e(c["role"])}</span>',
            f'<span class="meta">{e(cs["court"])} {e(when)} 선고 {e(cs["no"])} {e(kind)}'
            + (' · 전원합의체' if cs.get('en_banc') else '') + f' · {e(cs.get("disposition") or "")}'
            + (f' · {e(cs["gazette"])}' if cs.get('gazette') else '') + '</span>',
            f'<span class="chip {"ok" if c["confidence"] == "확실" else "warn"}">{e(c["confidence"])}</span>']
    if (c.get('status') or {}).get('current') is False:
        head.append(f'<span class="chip warn">바뀜 → {e(c["status"].get("overruled_by") or "")}</span>')
    P = [f'<section class="card" id="{e(a)}"><div class="head">{"".join(head)}</div>']
    if (c.get('status') or {}).get('scope'):
        P.append(row(a + '-scope', '바뀐 범위', e(c['status']['scope']), 'v s'))
    if c.get('cue'):
        P.append(row(a + '-cue', '단서', e(c['cue'])))
    if c.get('facts'):
        P.append(row(a + '-facts', '사안', '<br>'.join(e(x) for x in c['facts'])))
    P.append(row(a + '-rule', '법리', e(c['rule']), 'v d'))
    for i, rp in enumerate(c.get('rule_parts') or []):
        P.append(row(f'{a}-q{i + 1}', '원문 ' + str(i + 1), f'<b>{e(rp.get("part") or "")}</b> <q>{e(rp["quote"])}</q>', 'v s'))
    if c.get('result'):
        P.append(row(a + '-result', '결론', e(c['result'])))
    for i, t in enumerate(c.get('turn') or []):
        P.append(row(f'{a}-t{i + 1}', '갈림 ' + str(i + 1), e(t.get('fact', '')) + ' → ' + e(t.get('result', '')) + ' (' + link(t.get('ref', '')) + ')'))
    if c.get('not_decided'):
        P.append(row(a + '-nd', '말 안 함', e(c['not_decided']), 'v s'))
    for i, s in enumerate(c.get('asked') or []):
        lab = f'{EXAM.get(s["exam"], s["exam"])} {s["year"]} {s.get("subject", "")} 문{s["q"]}' + (f' 설문 {s["sub"]}' if s.get('sub') else '')
        P.append(row(f'{a}-k{i + 1}', '기출', e(lab) + f' · 유사도 {e(s.get("similarity", ""))}<br>' + e(s.get('diff', '')), 'v s'))
    arts = ', '.join(f'{x["law"]} 제{x["jo"]}조' + (f' 제{x["para"]}항' if x.get('para') else '') + (' (보조)' if x.get('role') == '보조' else '') for x in c.get('articles') or [])
    tail = ('조문 ' + arts if arts else '') + ((' · 같은 법리 ' + ', '.join(c['same_rule'])) if c.get('same_rule') else '')
    if tail:
        P.append(row(a + '-arts', '고리', e(tail), 'v s'))
    slots = ', '.join(f'{s["frame"].removeprefix("F-")} {s["node"]}({s["status"]})' for s in c.get('slots') or [])
    if slots:
        P.append(row(a + '-slots', '틀 자리', e(slots), 'v s'))
    bx = (c.get('editions') or {}).get('bar_extra')
    if bx:
        P.append(row(a + '-bar', '변시판', e(f'{bx["kind"]}: {bx["text"]}'), 'v s'))
    P.append('</section>')
    return '\n'.join(P)

n_ok = sum(1 for c in cards.values() if c['confidence'] == '확실')
P = ['<title>판례 카드 검수</title><meta name="claude:viewport-fit-sides" content="cover">',
     '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;800&family=IBM+Plex+Sans+KR:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap">',
     f'<style>{CSS}</style><div class="wrap">',
     '<h1>판례 카드 검수</h1>',
     f'<p class="lead">법행 민법 시범의 판례 카드 {len(cards)}장(팀 판정 확실 {n_ok})과 요건사실 틀 {len(frames)}개야. 0단계(법행 2023 민법 문2), 1단계(책임재산 보전, 민법 제404~407조), 2단계(소멸시효, 민법 제162~184조·제766조, 상법 제64조)에서 만들었어. 판례가 바뀐 카드는 지우지 않고 “바뀜”으로 남겼어. 틀마다 마디를 먼저 두고, 그 틀에 놓인 카드를 마디 순서로 이었어. 노란 글은 판결 이유에서 글자 그대로 딴 구절이야.</p>',
     '<ol class="look"><li>법리 문장이 판결이 한 말보다 넓거나 좁지 않은가</li><li>결론과 틀 자리(인정·배척·다시 심리)가 맞는가</li><li>갈림: 그 사실이면 정말 결론이 바뀌는가</li><li>기출 유사도(상·중·하)와 차이 설명이 맞는가</li><li>답안에 쓸 때 어색한 말, 빠진 판례</li></ol>',
     '<p class="hint" id="cmhint">줄 댓글을 준비하는 중이야.</p>',
     '<nav class="toc" aria-label="틀 목록">']
for fid in order:
    P.append(f'<a href="#{e(fid)}">{e(fid.removeprefix("F-"))} <span>마디 {len(frames[fid]["nodes"])} · 카드 {len(by_frame[fid])}</span></a>')
if loose:
    P.append(f'<a href="#loose">틀 밖 카드(구별·최근 등) <span>카드 {len(loose)}</span></a>')
P.append('</nav>')
for fid in order:
    fr = frames[fid]
    P.append(f'<h2 id="{e(fid)}">{e(fid.removeprefix("F-"))} <small>카드 {len(by_frame[fid])}</small></h2>')
    P.append(f'<div class="frame"><p class="lead ln" id="{e(fid)}-claim">{e(fr.get("claim", ""))}</p>')
    for nd in sorted(fr['nodes'], key=lambda n: (STAGE_ORDER.get(n['stage'], 9), int(n['id'].split('-')[-1]) if n['id'].split('-')[-1].isdigit() else 0)):
        basis = ', '.join(link(b) for b in nd.get('basis') or [])
        P.append(row(f'{fid}-{nd["id"]}', nd['id'], e(nd['element']) + f'<br><span class="meta">근거 {basis}</span>'))
    P.append('</div>')
    for c in sorted(by_frame[fid], key=lambda c: node_key(c, fid)):
        P.append(card_html(c))
if loose:
    P.append(f'<h2 id="loose">틀 밖 카드 <small>구별·최근 등, 카드 {len(loose)}</small></h2>')
    for c in sorted(loose, key=lambda c: (c['role'], c['id'])):
        P.append(card_html(c))
P.append('</div><script>' + widget + '</script>')
out.write_text('\n'.join(P), encoding='utf-8')
print(out, f'{out.stat().st_size // 1024}KB', f'틀 밖 {len(loose)}')
