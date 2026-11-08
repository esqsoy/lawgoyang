#!/usr/bin/env python3
"""영신 직검수 페이지: 카드마다 사례·설문·답안·조문·해설을 한 줄씩 보여 주고 줄마다 댓글을 받는다.

사용: python3 -I pipeline/review-page.py --out <파일>
Artifact로 올릴 때 capabilities: {comments: {}}. 줄을 누르면 입력칸이 열리고 Enter로 바로 Claude에게 간다(PRINCIPLES 8).
build.py가 만든 proto.html 안의 카드 데이터를 그대로 읽으므로, 먼저 build.py를 돌린다.
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
e = html.escape
out = Path(sys.argv[sys.argv.index('--out') + 1])
page = (ROOT / 'proto.html').read_text(encoding='utf-8')
D = json.loads(re.search(r'id="law-data" type="application/json">(.*?)</script>', page, re.S).group(1).replace('<\\/', '</'))
near = json.loads((ROOT / 'data' / 'near.json').read_text(encoding='utf-8'))
widget = (ROOT / 'pipeline' / 'comment-widget.js').read_text(encoding='utf-8')

CSS = """
/* 검수 장부: 카드 한 장이 한 블록, 줄 하나가 댓글 한 자리 */
:root{--paper:#f5f6f8;--sheet:#fff;--ink:#171c26;--muted:#586172;--rule:#d7dbe3;--navy:#24457a;--seal:#b0302a;--soft:#eef1f6;--hi:#fff5df;--hi-line:#bf9640;
--display:"Nanum Myeongjo","AppleMyungjo","Noto Serif KR",serif;--body:"IBM Plex Sans KR","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#11151c;--sheet:#192029;--ink:#e5e9ef;--muted:#9aa3b1;--rule:#2b333f;--navy:#a3bce6;--seal:#f08b82;--soft:#1f2732;--hi:#29231a;--hi-line:#c9a24a;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#11151c;--sheet:#192029;--ink:#e5e9ef;--muted:#9aa3b1;--rule:#2b333f;--navy:#a3bce6;--seal:#f08b82;--soft:#1f2732;--hi:#29231a;--hi-line:#c9a24a;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.6;word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:720px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:26px 64px;display:grid;gap:18px}
h1{font-family:var(--display);font-weight:800;font-size:1.7rem;margin:0}
p{margin:0}.lead{color:var(--muted);max-width:64ch}
h2{font-family:var(--display);font-size:1.2rem;margin:18px 0 0}h2 small{font-family:var(--body);font-size:.78rem;color:var(--muted);font-weight:400;margin-left:6px}
.card{background:var(--sheet);border:1px solid var(--rule);border-radius:12px;padding:14px 16px;display:grid;gap:6px;min-width:0}
.id{font-family:var(--mono);font-size:.76rem;color:var(--muted)}
.row{display:grid;grid-template-columns:3.6em 1fr;gap:8px;align-items:baseline;padding:2px 4px}
.k{font-size:.74rem;color:var(--navy);font-weight:600}
.v{font-family:var(--display);min-width:0}
.v.s{font-family:var(--body);font-size:.9rem;color:var(--muted)}
mark{background:var(--hi);color:inherit;border-bottom:2px solid var(--hi-line);padding:0 1px}
.hint{font-size:.86rem;color:var(--navy);background:var(--soft);border-radius:10px;padding:8px 12px}
body.cm-on .ln{cursor:text;border-radius:6px}
@media (hover:hover){body.cm-on .ln:hover{background:var(--soft)}}
.ln.on{background:var(--soft)}.ln.sent{box-shadow:inset 3px 0 0 var(--seal)}
.cbox{display:grid;gap:6px;margin:2px 0 6px;padding:8px;border:1px solid var(--navy);border-radius:10px;background:var(--sheet)}
.cbox textarea{font:inherit;font-size:16px;line-height:1.5;width:100%;box-sizing:border-box;min-height:44px;resize:none;border:1px solid var(--rule);border-radius:8px;padding:8px 10px;background:var(--paper);color:var(--ink)}
.cbox textarea:focus-visible,button:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.cbox .row{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;justify-content:space-between;grid-template-columns:none}
.cbox .st{font-size:.78rem;color:var(--muted);min-width:0}.cbox .st.ok{color:var(--navy)}.cbox .st.err{color:var(--seal)}
.cbox .go{font:inherit;font-size:.84rem;border:0;border-radius:8px;background:var(--navy);color:var(--sheet);padding:6px 14px;min-height:36px;cursor:pointer}
.cbox .go:disabled{opacity:.5;cursor:default}
"""

P = ['<title>법학고양 직검수</title><meta name="claude:viewport-fit-sides" content="cover">',
     '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;800&family=IBM+Plex+Sans+KR:wght@400;600&family=IBM+Plex+Mono&display=swap">',
     f'<style>{CSS}</style><div class="wrap">',
     '<h1>법학고양 직검수</h1>',
     f'<p class="lead">세트 {len(D["sets"])}개, 카드 {sum(len(x["cards"]) for x in D["sets"])}장. 답안·해설은 Claude 초안이야. 노랗게 표시한 자리가 게임에서 빈칸이 되는 조문이야(번호부터). 법적으로 틀린 곳, 어색한 답안, 빼거나 더할 해설, 근거 조문이 맞는지를 줄마다 달아 줘.</p>',
     '<p class="hint" id="cmhint">줄 댓글을 준비하는 중이야.</p>']


def row(id, k, v, cls='v'):
    return f'<div class="row ln" id="{e(id)}"><span class="k">{e(k)}</span><span class="{cls}">{v}</span></div>'


only = sys.argv[sys.argv.index('--sets') + 1].split(',') if '--sets' in sys.argv else None
# 검수 단계 요약(PRINCIPLES 1-2): 남은 단계가 있는 세트만 추가 작업한다
exam_sets = [st for st in D['sets'] if st.get('stages') and (not only or st['id'] in only)]
if exam_sets:
    names = [x['stage'] for x in exam_sets[0]['stages']]
    done_n = {n: sum(1 for st in exam_sets for x in st['stages'] if x['stage'] == n and x['state'] in ('통과', '고침')) for n in names}
    P.append('<section class="card" id="checks-summary"><div class="id">조문 층 검수 단계(세트 ' + str(len(exam_sets)) + '개) · 통과·고침 수</div>')
    P.append(row('checks-stages', '단계', e(' · '.join(f'{n} {done_n[n]}/{len(exam_sets)}' for n in names)), 'v s'))
    finished = [st['id'] for st in exam_sets if not st['todo']]
    P.append(row('checks-done', '재검수 없음', e(', '.join(finished) or '아직 없음'), 'v s'))
    for st in exam_sets:
        if st['todo']:
            P.append(row('checks-todo-' + st['id'], '남음', f'<a href="#{e(st["id"])}">{e(st["id"])}</a> ' + e(', '.join(st['todo'])), 'v s'))
    P.append('</section>')
for st in D['sets']:
    if only and st['id'] not in only:
        continue
    P.append(f'<h2 id="{e(st["id"])}">{e(st["title"])} <small>{e(st["label"])}{" · " + e(st["status"]) if st.get("status") else ""}</small></h2>')
    if st.get('stages'):
        chips = ' · '.join(f"{x['stage']} {x['state']}" + (f"({x['date']})" if x['date'] else '') for x in st['stages'])
        P.append(f'<p class="lead" id="{e(st["id"])}-stages">검수: {e(chips)}</p>')
    for i, b in enumerate(st.get('basis', [])):
        if b.get('none'):
            txt = f"설문 {b['sub']}: 바탕 판결 못 찾음(검색: {b.get('searched', '')}) · {b.get('checked', '')}"
        else:
            txt = (f"설문 {b['sub']}: {b['court']} {b['date']} 선고 {b['no']} {b.get('kind', '판결')} · 유사도 {b['similarity']} · {b['diff']}"
                   + (f" · 같은 법리 {', '.join(b['same_rule'])}" if b.get('same_rule') else '')
                   + (f" · 고친 것: {b['conflict']}" if b.get('conflict') else '') + f" · {b.get('checked', '')}")
        P.append(f'<p class="lead ln" id="{e(st["id"])}-basis{i + 1}">바탕 판결 {e(txt)}</p>')
    seen = set()
    for c in st['cards']:
        conf = f' · {c["conf"]}' if c.get('conf') else ''
        conf += f' · 판례연구 {c["research"]}' if c.get('research') else ''
        freq = f' · 빈출 {c["freq"]}' if c.get('freq') else ''
        P.append(f'<section class="card" id="{e(c["id"])}"><div class="id">{e(c["id"])} · {e(c["label"])}{e(freq)}{e(conf)} · 3단계 빈칸(첫 문구) {e(c["phrase"] or "자동")}</div>')
        if c['caseId'] not in seen:
            seen.add(c['caseId'])
            P.append(row(c['id'] + '-facts', '사례', e(c['facts']).replace('\n', '<br>')))
        P.append(row(c['id'] + '-q', '설문', e(c['q'])))
        P.append(row(c['id'] + '-a', '답안', e(c['prefix']) + '<mark>' + e(c['cite'] + ' ' + c['text']) + '</mark>' + e(c['suffix'])))
        for i, n in enumerate(c['note']):
            P.append(row(f'{c["id"]}-n{i + 1}', '해설', e(n), 'v s'))
        P.append(row(c['id'] + '-src', '출처', e(c['srcLine']) + ('<br>' + e(c['examSrc']) if c.get('examSrc') else ''), 'v s'))
        P.append('</section>')
    if st.get('later'):
        P.append(f'<section class="card" id="{e(st["id"])}-later"><div class="id">{e(st["id"])} · 나중 층(카드 없음, 데이터로만)</div>')
        for i, x in enumerate(st['later']):
            pr = ' / '.join(f"{p['court']} {p['date']} 선고 {p['no']} {p.get('kind', '판결')}({p['checked']})" for p in x.get('precedent', []))
            P.append(row(f'{st["id"]}-later{i + 1}', '층 ' + x['layer'], e(f"설문 {x['sub']}: {x['issue']}" + (f' · {pr}' if pr else '') + f" · {x.get('checked', '확인 필요')}"), 'v s'))
        P.append('</section>')
P.append('<section class="card" id="near"><div class="id">뜻은 맞음 짝(data/near.json) · ' + e(near['status']) + '</div>')
for k, v in near['pairs'].items():
    P.append(row('near-' + k, '짝', e(f'{k} ↔ {", ".join(v)}'), 'v s'))
for k, v in near['notes'].items():
    P.append(row('note-' + k, '메모', e(f'{k}: {v}'), 'v s'))
P.append('</section></div>')
P.append('<script>' + widget + '</script>')
out.write_text('\n'.join(P), encoding='utf-8')
print(out)
