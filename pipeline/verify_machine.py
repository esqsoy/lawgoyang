#!/usr/bin/env python3
"""검증틀 v3.2 1단계, 기계 층. 판례 카드(data/precedents), 요건사실 틀(data/frames), 판결 원문(sources/api/prec)을
읽어 기계 판정을 낸다. 카드와 틀은 고치지 않는다. 꼴이 맞는지는 precedent_check.py가 보고, 이 도구는 내용 대조를 한다.

사용:
  python3 -I pipeline/verify_machine.py                      카드 전부 → data/verify/machine-<오늘>.json, .md
  python3 -I pipeline/verify_machine.py --card '2023다240428#1'  한 장의 결과를 화면에(파일을 쓰지 않는다)
  python3 -I pipeline/verify_machine.py --headnotes          sources/api/prec/*.json에 headnote 칸을 채운다(cache의 전체 응답에서)
  python3 -I pipeline/verify_machine.py --selftest           pipeline/tests/verify의 일부러 틀린 카드가 모두 걸리는지 본다

결과 한 줄: {"card": 카드 id, "claim": 주장 id, "field": 주장 칸, "check": 검사 이름, "result": 맞음|후보|틀림, "basis": 근거}
- 맞음: 기계가 원문과 대조해 확인했다.
- 틀림: 기계가 정할 수 있는 규칙을 어겼다(주문 표기, 저장소에 원문이 없는 사건번호 등).
- 후보: 기계가 추렸다. 사람이 판정한다. 후보가 곧 오류는 아니다.
판시사항·판결요지 글은 결과에 옮기지 않는다(요지 번호와 글 일치도, 한정어 낱말만 적는다). 판결 이유 본문과 주문은 옮긴다.
"""
import argparse, collections, datetime, difflib, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = 'v3.2'
OK, CAND, BAD = '맞음', '후보', '틀림'
HEADNOTE_SOURCE = '대법원(법원도서관 작성), law.go.kr Open API'

# ---------------------------------------------------------------- 글 다루기

PUNCT = re.compile(r'[\s\.,·ㆍ\'"‘’“”「」『』()\[\]〈〉<>:;!?~\-–—/]')
CASE_KIND = ('다카|다|나|가합|가단|가소|두|누|구합|구단|구|도|노|고합|고단|마|라|카합|카단|카기|카|스|므|르|느|드|브|그|'
             '헌가|헌나|헌다|헌라|헌마|헌바|헌사|헌아|재다|재나|재두|머|민상|민재항|행상|형상|후|허|추|수|프|부|으|오|초|모')
NO = re.compile(r'(?<![0-9가-힣])((?:19|20)?\d{2}(?:' + CASE_KIND + r')\d{1,7})(?![0-9])')
DATE = re.compile(r'(?<!\d)((?:19|20)\d{2})\s*\.\s*(\d{1,2})\s*\.(?:\s*(\d{1,2})\s*\.?)?')
QUOTED = re.compile(r"‘([^’]{2,200})’|“([^”]{2,200})”|'([^']{2,200})'|\"([^\"]{2,200})\"|「([^」]{2,200})」")
ART_IN_TEXT = re.compile(r'([가-힣][가-힣ㆍ· ]*?(?:법|법률|규칙|령))\s*제(\d+)조(?:의(\d+))?(?:\s*제(\d+)항)?')


def sq(t):
    return PUNCT.sub('', t or '')


def ws(t):
    return re.sub(r'\s+', '', t or '')


def norm(t):
    return re.sub(r'\s+', ' ', t or '').strip()


def split_sents(t):
    """문장으로 나눈다. 괄호와 따옴표 안의 마침표, 날짜의 마침표(2023. 8. 31.)에서는 나누지 않는다."""
    t = t or ''
    out, depth, quote, start = [], 0, None, 0
    pairs = {'‘': '’', '“': '”', '「': '」'}
    for i, ch in enumerate(t):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in pairs:
            quote = pairs[ch]
        elif ch in '\'"':
            quote = ch
        elif ch in '(（':
            depth += 1
        elif ch in ')）':
            depth = max(0, depth - 1)
        elif ch == '.' and depth == 0:
            prev = t[i - 1] if i else ''
            nxt = t[i + 1] if i + 1 < len(t) else ''
            if nxt == '' or (nxt.isspace() and not prev.isdigit()):
                s = t[start:i + 1].strip()
                if s:
                    out.append(s)
                start = i + 1
    s = t[start:].strip()
    if s:
        out.append(s)
    return out


def top_parens(t):
    """가장 바깥 괄호 안의 글들."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(t or ''):
        if ch in '(（':
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch in ')）' and depth:
            depth -= 1
            if depth == 0:
                out.append(t[start:i])
    return out


JOSA = sorted(['으로부터', '로부터', '에게서', '에서는', '에서도', '으로서', '으로써', '이라고', '이라는', '에서', '에게', '으로', '까지', '부터',
               '처럼', '보다', '마다', '라고', '라는', '이나', '이란', '에는', '에도', '에만', '과는', '와는', '이며', '이고', '이다', '였다',
               '이라', '이면', '인지', '과', '와', '은', '는', '이', '가', '을', '를', '의', '에', '도', '만', '로', '나', '란', '며', '고',
               '들', '인', '적'], key=len, reverse=True)
VERB = re.compile(r'^([가-힣]{2,}?)(하|한|할|함|해|했|되|된|될|됨|돼|됐|시키|시킨|시켰|받|당하|당한|당했)')
# 카드를 쉬운 말로 쓰면서 들어온 낱말. 판결 글에 없어도 낱말 차집합에서 뺀다(뜻이 바뀌었는지는 A 경로가 문장으로 본다).
OUR_WORDS = set('''
그래서 그러나 그런데 그리고 따라서 그러므로 하지만 또한 다만 한편 그때 그날 그해 이때 이것 그것 여기 거기 이런 그런 이렇게 그렇게 어떤 어느 무엇 누가
때문 까닭 대하여 관하여 위하여 의하여 대한 관한 위한 의한 따라 따른 통하여 비추어 달리 같이 함께 모두 각각 서로 다시 이미 아직 먼저 나중 뒤에 앞서
있다 없다 한다 된다 않다 아니다 같다 본다 있는 없는 하는 되는 않는 아닌 같은 있었 없었 하였 되었 않았 있으 없으 하면 되면 않으 있고 없고 하고 되고
경우 사안 사건 판결 대법원 원심 문제 쟁점 결론 이유 근거 법리 요건 효과 판단 주장 사실 사정 것이 것은 것을 것으로 것이다 수는 수도 뿐이 만으
마치 마친 마쳤 넘겨 넘긴 넘어 갚 빚 빌려 빌린 돈 팔 판 샀 사들 받아 받은 주었 주어 준다 내어 내준 돌려 되돌 맡 맺 물어 묻 따져 따질 살펴 가려
지나 지난 지났 끝나 끝난 끝났 생긴 생겼 생기 없어 없앤 바뀌 바뀐 바꾼 바꾸 고쳐 고친 늘어 늘린 줄어 줄인 남은 남아 남긴 쓰인 쓰이 쓸 썼 적어 적은 적힌
알았 알고 알면 안 때 몰랐 모르 보아 보면 보았 본 볼 들어 들면 든다 들었 나온 나왔 나오 가진 가지 갖 걸린 걸려 다투 다툰 다퉜 이긴 이겼 졌 진다
깼 깨뜨 깬 옳 그르 틀렸 맞 잘못 뒤집 받아들 물리 내세 내세운 밝혔 밝힌 밝혀 정한 정해 정하 여긴 여겨 삼았 삼아 삼는 두었 둔 두고 놓 놓았
스스로 직접 바로 곧 결국 끝내 여전히 그대로 달라 다르 다른 새로 새 옛 뒤 앞 안 밖 위 아래 사이 동안 무렵 즈음 까지 부터 쪽 편 몫 값 셈
누구 아무 모든 온 여러 몇 둘 셋 하나 한쪽 양쪽 한꺼번에 따로 나눠 나누 합쳐 합친 더해 더한 뺀 빼고 넘는 넘지 넘어선 못한 못하 미치 이르 이른
사람 사람들 가운데 자기 자신 이름 차례 지금 처음 언제 상대 대신 종전 전후 시간 여럿 그로써 거꾸로 거꾸 주인 직전 직후 앞으로 요지 판례 전원합의체 전합 일반
실제 조금 번째 혼자 몰래 오래전 한참 자체 다섯 사서 보고 거슬러 유지 파기환송 계속 기준 전제 본래 보통 뒤에야 에야 에게서 그사 오랜 책임 원인 상태 기존 소액
'''.split())


# 조사처럼 끝나지만 그대로 두 글자 명사인 낱말(조사를 떼면 안 된다)
TWO = set('양도 인도 매도 효과 결과 합의 이의 원고 피고 상고 항고 경과 대가 고의 정의 협의 결의 동의 주의 과실 신고 통고 최고 권고 경고 보고 사이 차이 논의 거의 회의 '
          '제도 한도 용도 정도 태도 연도 압류 채무 담보 등기 점유 이자 원인 본인 타인 개인 법인 상인 증인 대리 관리 처리 수리 심리 법리 권리 승인 확인 부인 시인 오인 '
          '대위 행위 지위 범위 단위 주위 순위 우위 허위 차임 책임 위임 선의 악의 임의 유의 명의 주로 도로 선로 통로 별도 의도 기도 감나 누가 무과 사과 초과 '
          '통과 도과 부과 전가 평가 인가 허가 국가 대가 추가 증가 참가 가도 유가 원가 시가 호가 지가 주가 단가'.split())
ROOTS = ('같|넘|잃|팔|갚|빌리|빌려|마치|마쳤|받|주|내|맡|맺|묻|물|따지|따져|살피|살펴|가리|가려|지나|지났|끝나|끝났|생기|생겼|없애|없앴|바뀌|바뀐|바꾸|바꿨|고치|고쳤|늘|줄|남|쓰|썼|적|알|모르|몰랐|'
         '보|봤|들|나오|나왔|가지|가졌|갖|걸리|걸렸|다투|다퉜|이기|이겼|지|졌|깨|깼|옳|그르|틀리|틀렸|맞|뒤집|물리|내세우|내세웠|밝히|밝혔|정하|정했|여기|여겼|삼|두|놓|낳|잡|찾|챙기|'
         '되찾|되돌리|돌려주|돌려받|넘겨주|넘겨받|물려받|떠맡|떠안|이어받|건네|내주|내놓|들이|들어가|들어오|나가|나서|따르|따랐|미루|미뤘|늦|빠르|이르|닿|끊|잇|이었|막|막았|열|닫|'
         '세우|세웠|짓|지었|헐|허물|고르|골랐|뽑|빼|뺐|더하|보태|덜|나누|나눴|합치|합쳤|모으|모았|흩|쌓|매기|매겼|치르|치렀|물어주|갈음|그치|그쳤|멈추|멈췄|머무|벗어나|어기|어겼|지키|지켰|'
         '믿|속|속이|속였|숨기|숨겼|알리|알렸|밝|드러나|드러났|드러내|나타나|나타났|일어나|일어났|벌어지|벌어졌|이루|이뤘|이뤄|갖추|갖췄|채우|채웠|비우|비웠|메우|견주|견줘|겹치|겹쳤|'
         '어긋나|어긋났|엇갈리|맞서|맞섰|맞물|기대|기댔|힘입|말미암|비롯|걸치|걸쳤|거치|거쳤|미치|미쳤|끼치|끼쳤|입|입혔|덮|씌우|벗|풀|풀었|묶|묶였|얽|엮|달|달았|떼|뗐|붙|붙였|싣|실었|'
         '다르|달라|같|비슷|크|컸|작|많|적|높|낮|길|짧|넓|좁|쉽|어렵|새롭|옛|늦|이르|멀|가깝|무겁|가볍|세|약하|굳|뚜렷|분명|확실|마땅|마찬가지|그렇|이렇|어떻|아무렇')
ROOT_RE = re.compile(r'^(?:' + ROOTS + r'|있|없|않|아니|구하|말하|뜻하|이|것)[다고아어았었였은는을면지며게기던도서야으자니나음라려러요든므로써한할함해했된될됨워운울진질져졌인]{0,4}$')


def content_stems(text):
    """글의 내용어 어간. 괄호 속 글, 쉬운 말로 바꿔 쓰며 들어온 낱말, 한 글자 낱말은 뺀다."""
    out = []
    for tok in re.findall(r'[가-힣]{2,}', re.sub(r'\([^()]*\)', ' ', text or '')):
        s = stem(tok)
        if len(s) < 2 or s in OUR_WORDS or tok in OUR_WORDS or (tok not in TWO and len(tok) <= 5 and ROOT_RE.match(tok)):
            continue
        out.append((tok, s))
    return out


COPULA = ('이어서', '이므로', '이지만', '이었다', '이라고', '이라면', '이어야', '여서', '이다', '이니', '이라', '였다', '인지', '이던', '임', '다')
# 우리 말 서술어의 꼬리. 조사와 '○○하다' 꼴로 풀리지 않은 낱말이 이렇게 끝나면 판결 말을 쉬운 말로 바꾼 서술어로 보고 넘긴다.
PRED = re.compile(r'(는데|은데|던데|므로|면서|려면|더라도|더라|는지|은지|을지|어서|아서|여서|지만|도록|려고|거나|든지|다면|었고|았고|였고|으나|으니|으려|어야|아야|여야|어도|아도|여도|'
                  r'는다|[았었였겠했됐렸졌겼났왔갔냈섰쳤꿨췄혔웠]다|[았었였겠했됐렸졌겼났왔갔냈섰쳤꿨췄혔웠][고지으는던]|[가-힣]{1,3}[ㄴ-ㅎ]?다)$')
# 카드가 쓰는 줄임말 → 판결이 쓰는 말. 하나라도 원문에 있으면 있는 것으로 본다.
SYN = {'단기시효': ['단기소멸시효', '단기의소멸시효', '단기시효'], '상사시효': ['상사소멸시효', '상사채권', '상법제64조'], '시효기간': ['소멸시효기간', '시효기간', '소멸시효의기간'],
       '신의칙': ['신의성실', '신의칙'], '무자력': ['채무초과', '무자력'], '채무초과': ['채무초과', '무자력'], '대위채권자': ['채권자대위', '대위채권자', '대위하여'],
       '대위소송': ['채권자대위', '대위소송', '대위하여'], '이전등기': ['이전등기'], '등기명의인': ['등기명의', '소유명의', '명의인', '명의자'], '명의인': ['명의인', '명의자', '등기명의'],
       '확정판결': ['판결이확정', '확정된판결', '판결확정', '확정판결'], '취소소송': ['채권자취소', '사해행위취소', '취소소송'], '증명책임': ['입증책임', '증명책임'],
       '증명': ['입증', '증명'], '손해배상소송': ['손해배상'], '시효소멸': ['시효로소멸', '시효소멸', '소멸시효가완성'], '시효완성': ['시효가완성', '시효완성', '시효의완성'],
       '시효취득자': ['시효취득', '취득시효'], '부당이득반환': ['부당이득'], '말소청구': ['말소'], '이전등기청구': ['이전등기'], '인도청구': ['인도'], '대위청구': ['대위'],
       '피보전채권': ['피보전채권', '피보전권리', '보전될채권', '보전되는채권'], '피대위채권': ['피대위채권', '피대위권리', '대위행사'], '사해의사': ['사해의사', '사해의의사', '해함을알'],
       '추심금': ['추심'], '전부금': ['전부명령', '전부금'], '대여금': ['대여'], '대출금채권': ['대출'], '약정일': ['약정'], '확정일': ['확정'], '집행권원': ['집행권원', '채무명의'],
       '등기부취득시효': ['등기부취득시효', '등기부시효취득', '제245조제2항'], '손해배상청구권': ['손해배상청구권', '손해배상채권', '손해배상청구'], '부존재확인': ['부존재확인', '존재하지아니함을확인']}


def in_hay(tok, s, hay):
    if s in hay or tok in hay:
        return True
    m = VERB.match(s)
    if m and m.group(1) in hay:
        return True
    for e in COPULA:
        if tok.endswith(e) and len(tok) - len(e) >= 2 and (tok[:-len(e)] in hay or tok[:-len(e)] in OUR_WORDS):
            return True
    if any(x in hay for x in SYN.get(s, ())) or any(x in hay for k, v in SYN.items() if s.startswith(k) and len(s) - len(k) <= 2 for x in v):
        return True
    return bool(PRED.search(tok) or PRED.search(s))


def stem(tok):
    if tok in TWO:
        return tok
    for j in JOSA:
        if tok.endswith(j) and len(tok) > len(j):
            return tok[:-len(j)]
    return tok


def words_missing(text, hay):
    """text의 내용어 가운데 hay(sq한 원문)에 없는 것. 조사를 떼고, '○○하다·되다' 꼴은 앞의 명사만 본다."""
    out = []
    for tok, s in content_stems(text):
        if not in_hay(tok, s, hay) and s not in out:
            out.append(s)
    return out


def won_values(t):
    """글 속 금액을 원 단위 정수로. '200만 원'과 '2,000,000원'을 같게 본다."""
    vals = set()
    for m in re.finditer(r'(?:(\d[\d,]*)\s*억\s*)?(?:(\d[\d,]*)\s*만\s*)?(?:(\d[\d,]*)\s*천\s*)?(\d[\d,]*)?\s*원', t or ''):
        if not any(m.groups()):
            continue
        a, b, c, d = (int(x.replace(',', '') or 0) if x else 0 for x in m.groups())
        vals.add((a * 100000000 + b * 10000 + c * 1000 + d, m.group(0).strip()))
    return vals


def fz(t):
    """흐린 대조용 글: 문장부호·가림 표지를 지우고 판결 말투의 꼬리를 뗀다."""
    t = sq(t)
    t = re.sub(r'[○△□◇☆◎×●▲■]+|[A-Z](?=[가-힣])', '', t)
    return re.sub(r'라고할것이다|이라할것이다|라할것이다|고할것이다|할것인바|할것이므로|할것이고|할것이다|고봄이상당하다|고봄이타당하다|고보아야한다|고보아야할것이다', '', t)


def fuzzy(q, v):
    """q가 v 안에 얼마나 그대로 있나(0~1). q 길이만 한 창에서 순서를 지켜 겹치는 글자 수 / q 길이."""
    if not q or not v:
        return 0.0
    if q in v:
        return 1.0
    sm = difflib.SequenceMatcher(None, q, v, autojunk=False)
    m = sm.find_longest_match(0, len(q), 0, len(v))
    if m.size < 6:
        return m.size / len(q)
    slack = max(10, len(q) // 5)
    w = v[max(0, m.b - m.a - slack): m.b - m.a + len(q) + slack]
    return sum(b.size for b in difflib.SequenceMatcher(None, q, w, autojunk=False).get_matching_blocks()) / len(q)


def split_n(t):
    """'[1] … [2] …' 또는 '가. … 나. …' 꼴의 글을 {번호: 글}로. 번호가 없으면 {'1': 글}."""
    t = t or ''
    out = collections.OrderedDict()
    ms = list(re.finditer(r'\[(\d+)\]', t))
    if ms:
        for i, m in enumerate(ms):
            out[m.group(1)] = out.get(m.group(1), '') + t[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(t)]
        return out
    ms = list(re.finditer(r'(?:^|\n|/)\s*((?:[가-하]\.\s?)+)', t))
    if ms:
        for i, m in enumerate(ms):
            seg = t[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(t)]
            for k in re.findall(r'[가-하]', m.group(1)):
                out[k] = out.get(k, '') + seg
        return out
    return collections.OrderedDict({'1': t}) if t.strip() else out


def html_text(t):
    """API 응답의 글 칸 → 글. fetch_api.prec_body와 같은 규칙이다."""
    t = re.sub(r'<br\s*/?>', '\n', t or '', flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return '\n'.join(re.sub(r'[ \t ]+', ' ', x).strip() for x in t.split('\n')).strip()


# ---------------------------------------------------------------- 주문

ORDER = re.compile(r'【\s*주\s*문\s*】(.*?)【\s*이\s*유\s*】', re.S)
SELF = re.compile(r'(취소|변경)(하고|하며|한다)|항소를[^.]*기각|청구를[^.]*기각|(소|신청)를[^.]*각하|(지급|이행|인도|말소)하라|소송(은|을)[^.]*종료|확인한다')
COST = re.compile(r'(이 (상고기각 )?부분에 (관한|대한) )?(상고|소송|소송총|재항고)\s*비용|[가-힣() ]*(로|으로) 인한 소송총비용')
# 예외표(지침서 1-3): 기계가 '그 밖'으로 낸 주문을 가이가 정해 이유와 함께 둔다.
ORDER_EXCEPTIONS = {
    '91다37553': {'wording': '파기자판', 'scope': '일부',
                  'reason': '지침서 1-3 예외표. 주문이 원심 일부를 파기하고 그 부분 청구를 스스로 처리하면서 나머지 상고를 기각했는데, 옛 문체라 자판 표지가 읽히지 않는다'},
}


def order_flags(order):
    """주문 글 → 표지 다섯(지침서 1-3). 비용 구절은 떼고, 파기 문장은 '파기하고·파기한다'를 경계로 앞뒤를 따로 읽는다."""
    t = norm(order)
    f = {'appeal': '재항고' if '재항고' in t else '상고', 'broken': '없음', 'send': False, 'self': False, 'dismiss': False, 'reject': False}
    after = False
    for s in [x.strip() for x in re.split(r'(?<=다)\.\s*', t) if x.strip()]:
        s = COST.split(s)[0].strip()
        if not s:
            continue
        m = re.search(r'파기(하고|한다|하여)', s)
        if m:
            head, tail = s[:m.start()], s[m.end():]
            part = bool(re.search(r'원심(판결|결정)(의| 중)|부분', head))
            f['broken'] = '부분' if (part or f['broken'] == '부분') else '전부'
            if re.search(r'환송|이송', tail):
                f['send'] = True
            if SELF.search(tail):
                f['self'] = True
            after, rest = True, tail
        else:
            rest = s
            if after and re.search(r'환송|이송', s):
                f['send'] = True
            elif after and SELF.search(s) and not re.search(r'(상고|재항고)', s):
                f['self'] = True
        if re.search(r'(상고|재항고)[^.]*기각', rest):
            f['dismiss'] = True
        if re.search(r'(상고|재항고)[^.]*각하', rest):
            f['reject'] = True
    return f


def order_columns(f, no=None):
    """표지 → (문언 칸, 범위 칸, 보이는 표기, 예외 이유)."""
    ap = f['appeal']
    if f['broken'] == '없음':
        if f['reject'] and f['dismiss']:
            return f'{ap}각하·{ap}기각', '일부', f'일부 {ap}각하, 나머지 {ap}기각', None
        if f['reject']:
            return f'{ap}각하', '전부', f'{ap}각하', None
        if f['dismiss']:
            return f'{ap}기각', '전부', f'{ap}기각', None
        wording = '그 밖'
    elif f['send'] and f['self']:
        wording = '파기환송·자판'
    elif f['send']:
        wording = '파기환송'
    elif f['self']:
        wording = '파기자판'
    else:
        wording = '그 밖'
    scope = '일부' if (f['dismiss'] or f['reject']) else '전부'
    why = None
    if wording == '그 밖':
        ex = ORDER_EXCEPTIONS.get(no)
        if not ex:
            return '그 밖', None, None, None
        wording, scope, why = ex['wording'], ex['scope'], ex['reason']
    return wording, scope, ('일부 ' if scope == '일부' else '') + wording, why


# ---------------------------------------------------------------- 판결 원문 한 건

OPINION = re.compile(r'(?m)^[ \t]*(?:\d+\.\s*)?(?P<head>[^\n]{0,70}?(?:대법관|대법원판사)[^\n]{1,140}?의\s*(?:(?:다수|별개|반대)\s?의견에 대한\s*)?(?P<kind>별개|반대|보충)?\s*의견)'
                     r'(?:은 다음과 같다\.?)?[ \t]*$')
OPINION_INLINE = re.compile(r'(?:(?<=다\.)\s|\n)\s*(?P<head>(?:대법관|대법원판사)[^.\n]{2,80}?의\s*(?P<kind>별개|반대|보충)\s*의견)은 다음과 같다')
LOWER_HEAD = re.compile(r'원심의 판단|원심판결의 요지|원심판결 이유의 요지|원심이 인정한|원심의 사실인정|원심 판단')
LOWER_START = re.compile(r'^\s*(?:\(?\d{1,2}\)?[.)]?\s*|[가-하][.)]\s*|[①-⑳]\s*)*(?:원심은|원심판결은|원심법원은|원심의 판단은|제1심은|제1심법원은|원심이 (?!확정한|인정한|적법하게|채택한)[^,.]{0,60}(판단|판시|인정|배척|기각|인용)한)')
REASON = re.compile(r'잘못이 있|위법이 있|위법을 저지|수긍할 수 없|수긍하기 어렵|상고이유(의)? 주장은 이유 있|논지는 이유 있|법리를 오해|심리를 다하지')
SURNAME = '김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길연표왕금옥육맹탁국편용'
NAME_TAIL = set('은 는 이 가 을 를 의 에 도 만 로 나 다 자 여 고 지 와 과 며 면 서 에게 으로 였고 였다 이다 이며 에서 하여 하고 하는 하지 한다 등은 등이 등을 등의 측의 측은 측이'.split())
NAME_ROLE = re.compile(r'(?<![가-힣])(?:소외|망|亡|원고|피고|신청인|피신청인|재항고인|상대방|채무자|채권자|참가인|상속인|증인|매도인|매수인|수익자|전득자)\s?(?:\([^()]{1,12}\)\s?)?'
                       r'([' + SURNAME + r'][가-힣]{1,2})(?=[\s,.·ㆍ)(]|[은는이가을를의에과와로]|$)')
NOT_NAME = set('''소유 주장 명의 전부 조합 은행 이름 이외 모두 지분 한국 정부 국가 국민 서울 인천 사이 주식 회사 종중 문중 공사 공단 조치 이전 이후 전원 일부 본인 대리
전체 정당 지위 주소 소송 소외 원고 피고 채권 채무 권리 의무 인수 양수 양도 인정 지급 변제 선정 승계 한편 또는 이에 역시 고유 공동 연대 방어 이익 이행 제기 제출 주위
인도 정리 조정 은닉 유지 유효 전소 지상 지연 지체 한정 현재 현실 안에 위에 임의 임차 임대 전세 전득 주된 주채 구상 구체 민사 민법 모든 마찬 반대 반소 방법 배당 변론
신청 신고 신탁 심리 여부 여러 연체 오로 우선 위임 위탁 위법 육체 인과 장래 정확 제공 제외 조건 주택 지목 진정 차용 차임 채택 천만 추가 추심 표시 하자 허위 현물 황무'''.split())


class Src:
    """판결 원문 한 건: 주문, 구역표, 요지 칸."""

    def __init__(self, rec):
        self.rec, self.no = rec, rec.get('no')
        self.body = rec.get('body') or ''
        self.kind = rec.get('kind') or ''
        self.en_banc = '전원합의체' in self.kind
        self.bsq = sq(self.body)
        self._map()
        m = ORDER.search(self.body)
        self.order_text = norm(m.group(1)) if m else None
        self.flags = order_flags(self.order_text) if m else None
        self.columns = order_columns(self.flags, self.no) if m else ('그 밖', None, None, None)
        self.reason_start = m.end() if m else 0
        self._zones()
        hn = rec.get('headnote') or {}
        self.has_headnote = bool(hn)
        self.si = split_n(hn.get('판시사항'))
        self.yo = split_n(hn.get('판결요지'))
        self.yo_fz = {k: fz(v) for k, v in self.yo.items()}
        self.refs_articles = hn.get('참조조문') or rec.get('refs_articles') or ''
        self.refs_cases = hn.get('참조판례') or rec.get('refs_cases') or ''

    def _map(self):
        self.bws, self.pos = [], []
        for i, ch in enumerate(self.body):
            if not ch.isspace():
                self.bws.append(ch)
                self.pos.append(i)
        self.bws = ''.join(self.bws)

    def find(self, text):
        """글(띄어쓰기 무시)이 본문에 있는 자리. 없으면 -1."""
        return self.span(text)[0]

    def span(self, text):
        """글(띄어쓰기 무시)이 본문에서 차지하는 (처음, 끝). 없으면 (-1, -1)."""
        q = ws(text)
        i = self.bws.find(q) if q else -1
        return (self.pos[i], self.pos[i + len(q) - 1] + 1) if i >= 0 else (-1, -1)

    def _zones(self):
        b = self.body
        ops = [(m.start(), m.group('head'), m.group('kind')) for m in OPINION.finditer(b) if m.start() >= self.reason_start]
        ops += [(m.start('head'), m.group('head'), m.group('kind')) for m in OPINION_INLINE.finditer(b)
                if m.start() >= self.reason_start and not any(abs(m.start('head') - o[0]) < 5 for o in ops)]
        ops.sort()
        self.opinions = []
        for i, (st, head, kind) in enumerate(ops):
            names = [ws(x) for x in re.split(r'[,、]', re.sub(r'대법관|대법원판사|대법원장|(?<=[,\s])(?:동|같은|및)(?=\s)', '', re.split(r'의\s*(?:다수|별개|반대|보충)?\s?의견', head[re.search(r'대법관|대법원판사', head).start():])[0]))]
            self.opinions.append({'start': st, 'end': ops[i + 1][0] if i + 1 < len(ops) else len(b), 'head': norm(head),
                                  'kind': (kind + '의견') if kind else '의견(이름 없음)', 'names': [n for n in names if 2 <= len(n) <= 4]})
        self.maj_end = ops[0][0] if ops else len(b)
        self.sections = []
        want = 1
        for m in re.finditer(r'(?m)(?:^|(?<=】))[ \t]*(\d{1,2})\.[ \t]', b[self.reason_start:self.maj_end]):
            if int(m.group(1)) == want:
                st = self.reason_start + m.start()
                line = b[st: b.find('\n', st) if b.find('\n', st) > 0 else len(b)]
                self.sections.append({'n': want, 'start': st, 'head': norm(line)[:60]})
                want += 1

    def loc(self, pos):
        """자리 → 구역 이름."""
        if pos < 0:
            return None
        if pos < self.reason_start:
            j = re.search(r'【\s*주\s*문\s*】', self.body)
            return '주문' if j and pos >= j.start() else '머리'
        for o in self.opinions:
            if o['start'] <= pos < o['end']:
                return o['head']
        sec = [s for s in self.sections if s['start'] <= pos]
        return f"이유 {sec[-1]['n']}" if sec else '이유'

    def sentence_at(self, pos):
        b = self.body
        lo = max(0, pos - 2000)
        st = (b.rfind('\n', lo, pos) + 1) or lo
        for m in re.finditer(r'다\.\s', b[lo:pos]):
            st = max(st, lo + m.end())
        en = re.search(r'다\.(\s|$)', b[pos:])
        return st, (pos + en.end() if en else len(b))

    def para_at(self, pos):
        st = self.body.rfind('\n', 0, pos) + 1
        en = self.body.find('\n', pos)
        return st, (en if en >= 0 else len(self.body))

    def heading_before(self, pos):
        """자리 위쪽에서 가장 가까운 짧은 머리 줄(60자 안)."""
        best = None
        for m in re.finditer(r'(?m)^[ \t]*(?:\d{1,2}\.|[가-하]\.|\(\d+\)|\d+\))[ \t]*([^\n]{2,60})$', self.body[self.reason_start:pos]):
            best = m.group(1)
        return best

    def reversal_sentences(self):
        out = []
        maj = self.body[self.reason_start:self.maj_end]
        for m in REASON.finditer(maj):
            st, en = self.sentence_at(self.reason_start + m.start())
            s = norm(self.body[st:en])
            if s and not any(s == o['span'] for o in out):
                out.append({'loc': self.loc(st), 'span': s[:300]})
        return out

    def name_candidates(self):
        """가려지지 않은 개인 이름 후보. 역할 낱말 뒤의 성+이름 꼴만 본다. 대법관·대리인 이름은 대상이 아니다."""
        out = collections.Counter()
        head = self.body[:self.reason_start]
        def keep(tok):
            return (len(tok) == 3 and tok not in NOT_NAME and tok[:2] not in NOT_NAME and tok[1:] not in NAME_TAIL and tok[2:] not in NAME_TAIL
                    and not re.search(r'원고|피고|신청|상대|참가|소외|변호|법인|회사|조합|은행|종중|공사|주식|유한', tok))
        for m in re.finditer(r'【\s*(원고|피고|신청인|피신청인|재항고인|상대방|참가인|독립당사자참가인|채권자|채무자)[^】]*】([^\n(【]*)', head):
            party = re.split(r'소송대리인|담당변호사|변호사', m.group(2))[0]  # 대리인 이름은 직무로 나온 이름이라 대상이 아니다(26.11.28 이솝 판정: 헛후보 44개)
            for tok in re.split(r'[,\s]+', party):
                if re.fullmatch(r'[' + SURNAME + r'][가-힣]{2}', tok) and keep(tok):
                    out[tok] += 1
        for m in NAME_ROLE.finditer(self.body[self.reason_start:] + '\n' + ' '.join(str((self.rec.get('headnote') or {}).get(k) or '') for k in ('판시사항', '판결요지'))):
            if keep(m.group(1)):
                out[m.group(1)] += 1
        return out


# ---------------------------------------------------------------- 자료 읽기

class Ctx:
    def __init__(self, a, overlay=None):
        self.a = a
        self.today = datetime.date.fromisoformat(a.date)
        self.cards = collections.OrderedDict()
        for p in sorted(Path(a.cards).glob('*.json')):
            c = json.loads(p.read_text(encoding='utf-8'))
            if 'case' in c:
                self.cards[c['id']] = c
        for c in overlay or []:
            self.cards[c['id']] = c
        self.frames = collections.OrderedDict()
        for p in sorted(Path(a.frames).glob('*.json')):
            f = json.loads(p.read_text(encoding='utf-8'))
            self.frames[f['id']] = f
        self.srcs = {}
        for p in sorted(Path(a.prec).glob('*.json')):
            rec = json.loads(p.read_text(encoding='utf-8'))
            self.srcs[rec['no']] = Src(rec)
        self.by_case = collections.defaultdict(list)
        for c in self.cards.values():
            self.by_case[c['case']['no']].append(c)
        self.basis = {(f['id'], n['id']): list(n.get('basis') or []) for f in self.frames.values() for n in f.get('nodes', [])}
        self._ledger()
        self._sets()
        self._gazette()
        self.law_text = None
        self.rows, self.passed, self.skipped = [], collections.defaultdict(list), collections.defaultdict(list)

    def _ledger(self):
        self.ledger_keys = collections.defaultdict(set)
        p = Path(self.a.ledger)
        if not p.exists():
            self.ledger_keys = None
            return
        L = json.loads(p.read_text(encoding='utf-8'))

        def add(h):
            if h.get('exam') and h.get('year'):
                self.ledger_keys[(h['exam'], int(h['year']), str(h.get('q') or ''), str(h.get('sub') or ''))].add(h.get('part') or '')
        for sec in ('articles', 'archive'):
            for x in L.get(sec) or []:
                for h in x.get('hits') or []:
                    add(h)
        for sec in ('excluded', 'later'):
            for h in L.get(sec) or []:
                add(h)
        self.ledger_q = {(k[0], k[1], k[2]) for k in self.ledger_keys}

    def _sets(self):
        """세트 글에 나온 사건번호 → {(시험, 해, 과목, 문, 설문)}, 세트 basis의 등급."""
        self.set_cites = collections.defaultdict(set)
        self.set_basis = {}

        def walk(x, sub, out):
            if isinstance(x, dict):
                s = str(x.get('sub')) if x.get('sub') not in (None, '') else sub
                for v in x.values():
                    walk(v, s, out)
            elif isinstance(x, list):
                for v in x:
                    walk(v, sub, out)
            elif isinstance(x, str):
                for m in NO.finditer(x):
                    out[m.group(1)].add(sub)
        d = Path(self.a.sets)
        for p in sorted(d.glob('*.json')) if d.exists() else []:
            m = re.match(r'^([가-힣])(\d{4})-(.+)-([^-]+)$', p.stem)
            if not m:
                continue
            exam, year, subj, q = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            s = json.loads(p.read_text(encoding='utf-8'))
            out = collections.defaultdict(set)
            walk(s, '', out)
            for no, subs in out.items():
                for sub in subs:
                    self.set_cites[no].add((exam, year, subj, q, sub or ''))
            for b in s.get('basis') or []:
                if b.get('no') and b.get('similarity'):
                    self.set_basis[(exam, year, q, str(b.get('sub') or ''), b['no'])] = (b['similarity'], subj)

    def _gazette(self):
        """다른 판결의 참조판례·본문에 적힌 '(공…)' 표기를 사건번호별로 모은다. 값마다 적힌 판결의 수를 센다."""
        pat = re.compile(r'(?:선고|자)\s*([0-9]{2,4}[가-힣]{1,3}[0-9]+)(?:\s*,\s*[0-9가-힣]+)*\s*(?:전원합의체\s*)?(?:판결|결정)\s*\(\s*(공\s*[0-9][^()]{3,30}?)\)')
        found = collections.defaultdict(lambda: collections.defaultdict(set))
        texts = [(s.no, s.refs_cases + '\n' + s.body) for s in self.srcs.values()]
        cache = Path(self.a.cache) if self.a.cache else None
        if cache and cache.exists() and not self.a.no_cache:
            for p in cache.glob('prec-*.json'):
                no = p.stem[5:]
                if no in self.srcs:
                    continue
                try:
                    x = json.loads(p.read_text(encoding='utf-8')).get('PrecService') or {}
                except Exception:
                    continue
                texts.append((no, html_text(x.get('참조판례')) + '\n' + html_text(x.get('판례내용'))))
        for where, t in texts:
            for m in pat.finditer(t):
                if m.group(1) != where:
                    found[m.group(1)][re.sub(r'[\s,]', '', m.group(2))].add(where)
        self.gazette = found
        self.gazette_texts = len(texts)
        self.gazette_raw = {}
        for where, t in texts:
            for m in pat.finditer(t):
                self.gazette_raw.setdefault((m.group(1), re.sub(r'[\s,]', '', m.group(2))), norm(m.group(2)))

    def row(self, card, claim, field, check, result, basis):
        self.rows.append({'card': card, 'claim': claim, 'field': field, 'check': check, 'result': result, 'basis': basis})

    def ok(self, card, check):
        if check not in self.passed[card]:
            self.passed[card].append(check)

    def skip(self, card, check, why):
        self.skipped[card].append({'check': check, 'why': why})


def slots_of(c):
    return c.get('slots') or ([c['slot']] if c.get('slot') else [])


def slot_map(c):
    return {(s.get('frame'), s.get('node')): s.get('status') for s in slots_of(c)}


def same_rule_parts(n):
    """'2021다244[2]' → ('2021다244', '2')."""
    m = re.match(r'^(.+?)(?:\[([^\]]+)\])?$', n or '')
    return m.group(1), m.group(2)


FREE = ('cue', 'rule', 'result', 'not_decided')
META = re.compile(r'원심|대법원 유지|이 판결이|참조판례|변경|직접 판단|판단하지|전원합의체|전합|추론|계산')
WORKLOG = re.compile(r'(?<![가-힣])(?:이솝|파핀|울프|가이|영신|초이)(?=[가이은는의도과와,\s.)]|$)|검수|검토자|재검토|확인 필요|초안|작업 폴더|메모|TODO|다시 볼 것|주기 점검|역검색|역방향 점검|law\.go\.kr|원문을 읽고|검색으로 (찾|확인)')
RULE_NOTE = re.compile(r'\(변경|지금은|현재는|그대로 인용한다|전원합의체가|전합이|이 판결이 함께|이 부분은 [0-9]')
KNOWN_KEYS = {'id', 'role', 'case', 'holding', 'found_by', 'searched', 'name', 'cue', 'facts', 'rule', 'rule_parts', 'result', 'turn', 'not_decided',
              'slots', 'slot', 'articles', 'same_rule', 'asked', 'status', 'editions', 'confidence', 'checks', 'ev'}
FOUND_BY = {'검색', '기억 후보를 검색으로 확인', '세트 후보를 --case로 확인', '참조판례에서'}
QUALS = [('원칙적으로', r'원칙적으로|원칙으로|원칙상|원칙이'), ('특별한 사정이 없는 한', r'특별한 사정|특단의 사정|다른 사정이 없|특별한 사유'),
         ('다만(단서)', r'다만|그러나|하지만|그렇지만|단서'), ('할 수 있다', r'수\s*있'), ('할 수 없다', r'수\s*없|못\s?한다|못\s?하'),
         ('하여야 한다', r'여야\s*한|해야\s*한|야\s*한다|아니\s*된다|안\s*된다'), ('한하여·만', r'한하여|한정하여|한정된|한정되|한해|한한다|에만|뿐이|에 한정'),
         ('추정', r'추정'), ('간주', r'간주|의제'), ('예외', r'예외'), ('일반적으로', r'일반적으로|통상|보통'),
         ('반드시·당연히·곧바로', r'반드시|당연히|언제나|항상|곧바로|막바로'), ('…만으로', r'만으로'), ('적어도', r'적어도|최소한'),
         ('…하는 한', r'(?:하는|않는|없는|있는) 한[\s,]')]


def quals(t):
    return {name for name, pat in QUALS if re.search(pat, t or '')}


def own_text(tail, field, text):
    """문장 주장의 글에서, 따로 주장이 된 괄호(사건번호·메타 낱말이 든 괄호)를 뺀 것. 같은 것을 문장과 괄호에서 두 번 세지 않으려는 것이다."""
    if field == '괄호 속 주장' or not re.search(r'\.s\d+$', tail):
        return text
    for p in top_parens(text):
        if NO.search(p) or META.search(p):
            text = text.replace('(' + p + ')', ' ').replace('（' + p + '）', ' ')
    return text


def claims_of(c):
    """카드를 주장으로 쪼갠다(지침서 1-1). [(주장 id 꼬리, 칸, 글)]"""
    out = []

    def sents(field, text, name=None):
        for i, s in enumerate(split_sents(text)):
            out.append((f'{name or field}.s{i}', field, s))
            k = 0
            for p in top_parens(s):
                if NO.search(p) or META.search(p):
                    out.append((f'{name or field}.s{i}.p{k}', '괄호 속 주장', p))
                    k += 1
    sents('rule', c.get('rule'))
    for i, rp in enumerate(c.get('rule_parts') or []):
        out.append((f'rule_parts[{i}]', 'rule_parts', rp.get('quote') or ''))
    sents('result', c.get('result'))
    for i, f in enumerate(c.get('facts') or []):
        out.append((f'facts[{i}]', 'facts', f))
    sents('cue', c.get('cue'))
    for i, s in enumerate(slots_of(c)):
        out.append((f'slots[{i}]', 'slots', f"{s.get('frame')}/{s.get('node')}: {s.get('status')}"))
    for i, t in enumerate(c.get('turn') or []):
        out.append((f'turn[{i}]', 'turn', f"{t.get('fact')} → {t.get('result')} ({t.get('ref')})"))
    for i, n in enumerate(c.get('same_rule') or []):
        out.append((f'same_rule[{i}]', 'same_rule', n))
    sents('not_decided', c.get('not_decided'))
    st = c.get('status') or {}
    sents('scope', st.get('scope'))
    out.append(('status.current', 'status', str(st.get('current'))))
    bx = (c.get('editions') or {}).get('bar_extra')
    if bx:
        sents('bar_extra', bx.get('text'))
        out.append(('bar_extra.kind', 'bar_extra', bx.get('kind') or ''))
    for i, h in enumerate(c.get('asked') or []):
        out.append((f'asked[{i}].similarity', 'asked', h.get('similarity') or ''))
        out.append((f'asked[{i}].diff', 'asked', h.get('diff') or ''))
    for i, x in enumerate(c.get('articles') or []):
        out.append((f'articles[{i}].role', 'articles', f"{x.get('law')} 제{x.get('jo')}조 {x.get('role')}"))
    out.append(('omit', 'omit', ''))
    for k in ('case.disposition', 'case.gazette', 'case', 'holding', 'role', 'found_by', 'searched'):
        out.append((k, k.split('.')[0], ''))
    return out


def field_hashes(ctx, c, src):
    """칸마다 해시: 카드 칸 + 원문 판본(판례일련번호·받은 날) + 걸린 틀 마디 + ref 카드. 하나라도 바뀌면 그 칸의 '검증됨'이 무효다."""
    ver = [src.rec.get('serial'), src.rec.get('fetched')] if src else None

    def h(*x):
        return hashlib.sha256(json.dumps([ver, *x], ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    refs = [(t.get('ref'), {k: ctx.cards[t['ref']].get(k) for k in ('rule', 'result', 'status')} if t.get('ref') in ctx.cards else None) for t in c.get('turn') or []]
    nodes = [(s.get('frame'), s.get('node'), next((n for n in (ctx.frames.get(s.get('frame')) or {}).get('nodes', []) if n.get('id') == s.get('node')), None))
             for s in slots_of(c)]
    out = {k: h(c.get(k)) for k in ('case', 'holding', 'cue', 'facts', 'rule', 'rule_parts', 'result', 'not_decided', 'articles', 'asked', 'same_rule')}
    out['turn'] = h(c.get('turn'), refs)
    out['slots'] = h(slots_of(c), nodes)
    ob = (c.get('status') or {}).get('overruled_by')
    out['status'] = h(c.get('status'), {k: ctx.cards[ob].get(k) for k in ('rule', 'status')} if ob in ctx.cards else None)
    out['bar_extra'] = h((c.get('editions') or {}).get('bar_extra'))
    return out


# ---------------------------------------------------------------- 카드 한 장 검사

def check_card(ctx, c):
    cid = c['id']
    case = c.get('case') or {}
    no = case.get('no')
    src = ctx.srcs.get(no)
    R, okc = ctx.row, ctx.ok
    C = lambda tail: f'{cid}/{tail}'
    claims = claims_of(c)
    st = c.get('status') or {}
    bx = (c.get('editions') or {}).get('bar_extra')

    # --- 덮음: 카드의 모든 칸과 문장이 주장에 걸리는가
    cover = True
    for k in c:
        if k not in KNOWN_KEYS:
            R(cid, C(k), k, '덮음', CAND, f'주장 표(지침서 1-1)에 없는 칸 {k}이 카드에 있다')
            cover = False
    if c.get('name'):
        R(cid, C('name'), 'name', '덮음', CAND, 'name 칸에 글이 있는데 주장 표에 이 칸의 판정문이 없다')
        cover = False
    parts = c.get('rule_parts') or []
    part_hay = [sq((rp.get('part') or '') + (rp.get('quote') or '')) for rp in parts]
    sents = [(i, s, content_stems(s)) for i, s in enumerate(split_sents(c.get('rule')))]
    sents = [x for x in sents if len(x[2]) >= 3]
    score = {(i, j): sum(1 for tk, sm in toks if in_hay(tk, sm, hay)) / len(toks) for i, s, toks in sents for j, hay in enumerate(part_hay)}
    owned = {max(sents, key=lambda x: score[(x[0], j)])[0] for j in range(len(part_hay))} if sents else set()
    allhay = ' '.join(part_hay)
    for i, s, toks in sents:
        best, bi = max(((score[(i, j)], j) for j in range(len(part_hay))), default=(0.0, None))
        miss = [sm for tk, sm in toks if not in_hay(tk, sm, allhay)]
        run = longest = 0
        for tk, sm in toks:
            run = run + 1 if sm in miss else 0
            longest = max(longest, run)
        if best < 0.5:
            R(cid, C(f'rule.s{i}'), 'rule', '덮음', CAND,
              f'rule 문장 {i}을 받치는 마디가 없다(가장 가까운 마디 {bi}, 낱말 겹침 {best:.2f}). 문장: {s[:80]}')
            cover = False
        elif i not in owned and best < 0.8:
            R(cid, C(f'rule.s{i}'), 'rule', '덮음', CAND,
              f'rule 문장 {i}에 딸린 마디가 없다(마디는 모두 다른 문장에 더 가깝다. 가장 가까운 마디 {bi}, 낱말 겹침 {best:.2f}). 문장: {s[:80]}')
            cover = False
        elif longest >= 5:
            R(cid, C(f'rule.s{i}'), 'rule', '덮음', CAND,
              f'rule 문장 {i}에 어느 마디에도 없는 낱말이 이어진다({longest}개): {", ".join(miss[:8])}')
            cover = False
    if cover:
        okc(cid, '덮음')

    # --- 꼴: 닫힌 값
    if c.get('found_by') not in FOUND_BY:
        R(cid, C('found_by'), 'found_by', '닫힌 값', BAD, f"found_by '{c.get('found_by')}'가 정해진 값이 아니다")
    elif c.get('found_by') == '검색' and not c.get('searched'):
        R(cid, C('searched'), 'searched', '닫힌 값', CAND, 'found_by가 검색인데 searched가 비었다')
    else:
        okc(cid, '닫힌 값')
    if c.get('role') == '최근' and case.get('date'):
        try:
            d = datetime.date.fromisoformat(case['date'])
            limit = 10 if case.get('en_banc') else 5
            if (ctx.today - d).days > limit * 365.25:
                R(cid, C('role'), 'role', "role '최근' 기한", CAND,
                  f"선고일 {case['date']}, {'전합' if case.get('en_banc') else '소부'} 기준 {limit}년을 넘었다. '바탕'으로 다시 매길 후보(지침서 8-3의 10)")
            else:
                okc(cid, "role '최근' 기한")
        except ValueError:
            pass

    # --- cue: 쟁점 문장만 있는가
    cs = split_sents(c.get('cue'))
    issue = re.compile(r'(문제 ?(다|이다|된다|가 된다)|쟁점이다|따져야 한다|다투어진다|살펴야 한다|판단하여야 한다)\.?$')
    if cs and all(issue.search(norm(s)) for s in cs):
        R(cid, C('cue.s0'), 'cue', 'cue 쟁점 문장', CAND, f'cue가 사실 없이 쟁점 문장뿐이다(지침서 1-7의 3): {norm(c.get("cue"))[:80]}')
    elif cs:
        okc(cid, 'cue 쟁점 문장')

    # --- 작업 기록 낱말, rule 속 변경 주석
    hit = False
    for tail, field, text in claims:
        text = own_text(tail, field, text)
        if field in ('rule', 'result', 'cue', 'facts', 'not_decided', 'scope', 'bar_extra', '괄호 속 주장') and tail != 'bar_extra.kind':
            m = WORKLOG.search(text)
            if m:
                R(cid, C(tail), field, '작업 기록 낱말', CAND, f"'{m.group(0)}': {text[:90]}")
                hit = True
        if field == 'rule' or (field == '괄호 속 주장' and tail.startswith('rule')):
            m = RULE_NOTE.search(text) or NO.search(text)
            if m:
                R(cid, C(tail), 'rule', 'rule 속 주석', CAND, f"rule에 판례 변경 주석이나 다른 판결 이야기로 보이는 글('{m.group(0)}'): {text[:90]}")
                hit = True
    if not hit:
        okc(cid, '작업 기록 낱말')
        okc(cid, 'rule 속 주석')

    # --- 글 속 사건번호: 저장소에 원문이 있는가, 카드 id가 있는가, '이 판결이 든' 번호가 본문에 있는가
    hit = False
    for tail, field, text in claims:
        if field in ('slots', 'articles', 'asked', 'same_rule', 'status', 'omit', 'rule_parts') or not text:
            continue
        text = own_text(tail, field, text)
        for m in re.finditer(r'((?:19|20)?\d{2}(?:' + CASE_KIND + r')\d{1,7})#(\d+|[가나다라마바사아자차카타파하])', text):
            if m.group(0) not in ctx.cards and field != 'turn':
                R(cid, C(tail), field, '글 속 카드 id', BAD, f'{m.group(0)} 카드가 저장소에 없다')
                hit = True
        for n in dict.fromkeys(m.group(1) for m in NO.finditer(text)):
            if n == no:
                continue
            if n not in ctx.srcs:
                R(cid, C(tail), field, '글 속 사건번호 원문', BAD, f'{n}의 원문이 저장소에 없다(받아 오거나 번호를 뺀다): {text[:70]}')
                hit = True
            if (src and field != 'scope' and not tail.startswith('scope') and n not in src.body and n not in src.refs_cases
                    and re.search(r'이 판결이 [^.,]{0,14}(든|들고|들었|인용|참조|따른|따랐|원용|변경)|참조판례로', text)):
                R(cid, C(tail), field, '괄호 속 사건번호 인용', CAND, f'이 판결이 {n}을 들었다고 적었는데 본문과 참조판례 칸에 그 번호가 없다')
                hit = True
    ob = st.get('overruled_by')
    if ob and ob.split('#')[0] not in ctx.srcs:
        R(cid, C('status.overruled_by'), 'status', '글 속 사건번호 원문', BAD, f'overruled_by {ob}의 원문이 저장소에 없다')
        hit = True
    if not hit:
        okc(cid, '글 속 사건번호 원문')

    # --- same_rule
    refs_turn = {(t.get('ref') or '').split('#')[0] for t in c.get('turn') or []}
    mine = slot_map(c)
    for i, raw in enumerate(c.get('same_rule') or []):
        n, hn = same_rule_parts(raw)
        clean = True
        if n not in ctx.srcs:
            R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule 원문', BAD, f'{n}의 원문이 저장소에 없다(받아 온 뒤 쌍 단위로 판정한다)')
            clean = False
        if n in refs_turn:
            R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule과 turn 겹침', CAND, f'{n}이 turn의 ref에도 있다. 같은 법리이면서 결론이 갈린다고 적은 셈이다')
            clean = False
        if n == no:
            R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule과 turn 겹침', CAND, '자기 판결을 same_rule에 적었다')
            clean = False
        others = [o for o in ctx.by_case.get(n, []) if not hn or str(o.get('holding')) == hn]
        dead = [o['id'] for o in others if (o.get('status') or {}).get('current') is False]
        part = [o['id'] for o in ctx.by_case.get(n, []) if (o.get('status') or {}).get('scope') or (o.get('status') or {}).get('current') is False]
        if dead:
            R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule 변경 표기', CAND,
              f'{raw}: 상대 판결 카드 {", ".join(dead)}가 current false다. 바뀐 요지를 같은 법리로 들었으면 not_decided로 옮긴다(지침서 8-3의 3)')
            clean = False
        elif part and not hn:
            R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule 변경 표기', CAND,
              f'{raw}: 일부가 바뀐 판결이다({", ".join(part)}에 scope). 바뀌지 않은 요지이면 번호[요지] 꼴로 적는다')
            clean = False
        for o in others:
            theirs = slot_map(o)
            sh = set(mine) & set(theirs)
            opp = [(k[1], mine[k], theirs[k]) for k in sh if {mine[k], theirs[k]} == {'인정', '배척'}]
            if opp:
                R(cid, C(f'same_rule[{i}]'), 'same_rule', 'same_rule 방향', CAND,
                  f"{o['id']}와 같은 마디에서 상태가 반대다: " + ', '.join(f'{a} 이 카드 {b}·상대 {d}' for a, b, d in opp))
                clean = False
        if clean:
            okc(cid, 'same_rule')

    # --- turn
    for i, t in enumerate(c.get('turn') or []):
        ref = (t.get('ref') or '').strip()
        clean = True
        if ref in ctx.cards:
            o = ctx.cards[ref]
            if (o.get('status') or {}).get('current') is False:
                R(cid, C(f'turn[{i}]'), 'turn', 'turn ref 현행', CAND, f'ref {ref}가 current false 카드다. 현행 카드로 돌린 뒤 결론이 다른지 다시 본다')
                clean = False
            if o['case']['no'] == no:
                R(cid, C(f'turn[{i}]'), 'turn', '같은 판결 turn', CAND, f'ref {ref}가 같은 판결의 다른 요지다. 판결이 스스로 두 갈래를 나눠 말했을 때만 turn이다')
                clean = False
            theirs = slot_map(o)
            sh = sorted(set(mine) & set(theirs))
            if sh and all(mine[k] == theirs[k] for k in sh):
                R(cid, C(f'turn[{i}]'), 'turn', '같은 마디·같은 상태 turn', CAND,
                  f'ref {ref}와 같이 걸린 마디({", ".join(k[1] for k in sh)})의 상태가 모두 같다({mine[sh[0]]}). 결론이 다른지 본다')
                clean = False
            elif not sh:
                ctx.skip(cid, 'turn 방향', f'turn[{i}] ref {ref}와 같이 걸린 마디가 없어 상태를 비교하지 못했다')
            if difflib.SequenceMatcher(None, sq(t.get('result')), sq(c.get('result'))).ratio() >= 0.8:
                R(cid, C(f'turn[{i}]'), 'turn', '같은 마디·같은 상태 turn', CAND, 'turn의 result가 이 카드의 result와 거의 같은 글이다')
                clean = False
        elif '#' in ref and ref.split('#')[0] not in ctx.srcs:
            R(cid, C(f'turn[{i}]'), 'turn', '글 속 사건번호 원문', BAD, f'ref {ref}의 원문이 저장소에 없다')
            clean = False
        if re.search(r'문제 ?(된다|가 된다|다)\.?$', norm(t.get('result'))):
            R(cid, C(f'turn[{i}]'), 'turn', 'turn 이웃 쟁점', CAND, f"result가 '…가 문제 된다'로 끝난다(결론이 아니라 이웃 쟁점): {norm(t.get('result'))[:60]}")
            clean = False
        if clean:
            okc(cid, 'turn')

    # --- 현행성과 일관성
    scope = st.get('scope') or ''
    if st.get('current') is False and re.search(r'범위 밖|남은 부분|그대로|변경 대상이 아니|일부', scope):
        mates = []
        for o in ctx.cards.values():
            so = o.get('status') or {}
            if o['id'] != cid and (so.get('overruled_by') == st.get('overruled_by') or (st.get('overruled_by') or '#').split('#')[0] in (so.get('scope') or '')):
                mates.append(f"{o['id']} current {str(so.get('current')).lower()}")
        R(cid, C('status.current'), 'status', '일관성(일부 변경)', CAND,
          'current false인데 scope가 바뀌지 않은 부분이 있다고 적는다. 일부 변경은 current true + scope가 원칙이다(지침서 1-12). '
          + (f'같은 변경 판결에 걸린 카드: {"; ".join(mates[:6])}' if mates else ''))
    elif st.get('current') is False or scope:
        okc(cid, '일관성(일부 변경)')
    sib = [o for o in ctx.by_case.get(no, []) if o['id'] != cid]
    changed = [o['id'] for o in sib if (o.get('status') or {}).get('current') is False or (o.get('status') or {}).get('scope')]
    if changed and st.get('current') is not False and not scope:
        R(cid, C('scope'), 'status', '일관성(같은 판결 다른 요지)', CAND,
          f'같은 판결의 카드 {", ".join(changed)}에 변경 표시가 있는데 이 카드에는 scope가 없다(이 요지가 범위 밖이면 그렇게 적는다)')
    if st.get('current') is False:
        used = [f'{k[0]}/{k[1]}' for k, bs in ctx.basis.items() if cid in bs]
        if used:
            R(cid, C('status.current'), 'status', '틀 basis 현행', CAND, f'current false 카드가 틀 마디의 근거로 남아 있다(틀 근거에서 뺀다, 지침서 1-8 경계 5): {", ".join(used)}')
        else:
            okc(cid, '틀 basis 현행')
    if src:
        dead = sorted({o['id'] for n in set(NO.findall(src.refs_cases)) if n != no for o in ctx.by_case.get(n, [])
                       if (o.get('status') or {}).get('current') is False})
        if dead:
            R(cid, C('status.current'), 'status', '참조판례 변경 경고', CAND, f'이 판결이 참조판례로 든 판결의 카드가 current false다: {", ".join(dead)}. 이 카드의 법리가 그 변경에 걸리는지 본다')
        else:
            okc(cid, '참조판례 변경 경고')

    # --- slot과 틀 basis
    for i, s in enumerate(slots_of(c)):
        k = (s.get('frame'), s.get('node'))
        if k in ctx.basis and cid not in ctx.basis[k] and st.get('current') is not False:
            R(cid, C(f'slots[{i}]'), 'slots', 'slot과 틀 basis', BAD, f'{k[0]}/{k[1]}에 slot이 있는데 그 마디 basis에 이 카드가 없다(지침서 8-3의 1)')
        elif k in ctx.basis:
            okc(cid, 'slot과 틀 basis')
    for k, bs in ctx.basis.items():
        if cid in bs and k not in mine:
            R(cid, C('slots'), 'slots', '틀 basis에만 있음', CAND, f'{k[0]}/{k[1]}의 basis에 이 카드가 있는데 그 마디 slot이 없다. 사안이 그 마디를 다투지 않았거나 모듈 틀을 건너 가리킨 경우만 된다')

    # --- asked와 원장, 세트
    rank = {'상': 3, '중': 2, '하': 1}
    have = set()
    for i, h in enumerate(c.get('asked') or []):
        key = (h.get('exam'), int(h.get('year') or 0), str(h.get('q') or ''), str(h.get('sub') or ''))
        have.add(key)
        if ctx.ledger_keys is not None:
            ps = ctx.ledger_keys.get(key)
            if not ps:
                R(cid, C(f'asked[{i}]'), 'asked', 'asked와 원장', CAND,
                  f"{h.get('exam')}{h.get('year')} {h.get('subject')} 문{h.get('q')} 설문{h.get('sub')}이 원장에 없다" + (' (그 문은 있다)' if key[:3] in ctx.ledger_q else ''))
            elif not any((h.get('subject') or '') in p for p in ps):
                R(cid, C(f'asked[{i}]'), 'asked', 'asked와 원장', CAND, f"설문은 원장에 있는데 과목이 다르다: 카드 {h.get('subject')}, 원장 {sorted(ps)}")
            else:
                okc(cid, 'asked와 원장')
        sb = ctx.set_basis.get((key[0], key[1], key[2], key[3], no))
        if sb and rank.get(h.get('similarity'), 0) < rank.get(sb[0], 0):
            R(cid, C(f'asked[{i}].similarity'), 'asked', '세트 basis와 등급', CAND, f"카드 유사도 {h.get('similarity')}가 세트 basis의 {sb[0]}보다 낮다(카드가 세트보다 낮을 수는 없다, 지침서 1-15)")
        if not re.match(r'^\s*결론 (같음|반대)', h.get('diff') or ''):
            R(cid, C(f'asked[{i}].diff'), 'asked', 'diff 첫머리', CAND, "diff 첫머리에 '결론 같음' 또는 '결론 반대(바뀐 사실: …)'가 없다(지침서 1-15의 2)")
        else:
            okc(cid, 'diff 첫머리')
    return claims


def check_case_level(ctx, c, src):
    """원문이 있어야 하는 검사들."""
    cid = c['id']
    case = c.get('case') or {}
    no = case.get('no')
    R, okc = ctx.row, ctx.ok
    C = lambda tail: f'{cid}/{tail}'
    st = c.get('status') or {}
    bx = (c.get('editions') or {}).get('bar_extra')
    body = src.body
    hold = str(c.get('holding'))

    # --- case 칸
    bad = []
    if case.get('court') != src.rec.get('court'):
        bad.append(f"법원 {case.get('court')}≠{src.rec.get('court')}")
    if re.sub(r'\D', '', case.get('date') or '') != re.sub(r'\D', '', src.rec.get('date') or ''):
        bad.append(f"선고일 {case.get('date')}≠{src.rec.get('date')}")
    if bool(case.get('en_banc')) != src.en_banc:
        bad.append(f"전합 {case.get('en_banc')}≠원문 종류 '{src.kind}'")
    if case.get('kind') != src.kind.replace('전원합의체', '').strip():
        bad.append(f"종류 {case.get('kind')}≠{src.kind}")
    if bad:
        R(cid, C('case'), 'case', 'case 칸', BAD, '; '.join(bad))
    else:
        R(cid, C('case'), 'case', 'case 칸', OK, f"법원·선고일·종류·전합이 원문 기록과 같다(판례일련번호 {src.rec.get('serial')}, 받은 날 {src.rec.get('fetched')})")

    # --- 주문
    wording, scope_col, shown, why = src.columns
    f = src.flags
    if not src.order_text:
        R(cid, C('case.disposition'), 'case', '주문', CAND, '원문에서 주문을 찾지 못했다')
    elif wording == '그 밖':
        R(cid, C('case.disposition'), 'case', '주문', CAND, f"주문을 닫힌 표기로 읽지 못했다(그 밖). 가이가 정해 예외표에 둔다. 카드: {case.get('disposition')}. 주문: {src.order_text[:200]}")
    elif shown == case.get('disposition'):
        R(cid, C('case.disposition'), 'case', '주문', OK, f'문언 칸 {wording}, 범위 칸 {scope_col}, 표기 {shown}' + (f' (예외표: {why})' if why else ''))
    else:
        R(cid, C('case.disposition'), 'case', '주문', BAD,
          f"카드 '{case.get('disposition')}' ≠ 기계 '{shown}'(문언 칸 {wording}, 범위 칸 {scope_col}). 주문: {src.order_text[:220]}")
    if f:
        r = c.get('result') or ''
        says_break = bool(re.search(r'파기|깼|깨뜨|원심(은|이|의 판단은)? ?(잘못|틀렸|위법)|수긍할 수 없', r))
        says_keep = bool(re.search(r'상고를? ?기각|원심(의 결론|의 판단|판결)?(을|이|은)? ?(유지|옳|정당|맞)|수긍(하|할 수 있|된)|원심이 옳', r))
        hit = False
        if says_break and f['broken'] == '없음':
            R(cid, C('result'), 'result', 'result와 주문', CAND, f'result는 원심을 깼다고 하는데 주문에 파기가 없다({shown}). result: {r[:80]}')
            hit = True
        if says_keep and not says_break and f['broken'] == '전부' and not (f['dismiss'] or f['reject']):
            R(cid, C('result'), 'result', 'result와 주문', CAND, f'result는 원심 유지만 말하는데 주문은 원심 전부를 깼다({shown}). result: {r[:80]}')
            hit = True
        if scope_col == '일부' and f['broken'] != '없음' and not (says_break and says_keep):
            R(cid, C('result'), 'result', "result와 주문('일부'의 두 갈래)", CAND,
              f"범위 칸이 일부다({shown}). result에 깨진 갈래와 유지된 갈래가 둘 다 있어야 하는데 {'깨진' if says_break else '유지된' if says_keep else '어느'} 갈래만 읽힌다. result: {r[:80]}")
            hit = True
        for i, s in enumerate(slots_of(c)):
            if s.get('status') == '다시 심리(파기환송)' and f['broken'] == '없음':
                R(cid, C(f'slots[{i}]'), 'slots', 'slot과 주문', BAD, f"주문에 파기가 없는데({shown}) slot 상태가 '다시 심리(파기환송)'다")
                hit = True
        if not hit:
            okc(cid, 'result와 주문')

    # --- quote: 자리, 원심 문단, 다수의견 구역, 잘린 단서
    quotes = []
    for i, rp in enumerate(c.get('rule_parts') or []):
        q = rp.get('quote') or ''
        pos = src.find(q)
        quotes.append((i, q, pos))
        if pos < 0:
            R(cid, C(f'rule_parts[{i}]'), 'rule_parts', 'quote 자리', BAD, f'quote가 본문에 없다: {q[:50]}')
            continue
        flags = []
        if pos < src.reason_start:
            flags.append('quote가 이유가 아니라 머리·주문에 있다')
        if pos >= src.maj_end:
            flags.append(f'quote가 다수의견 구역 밖에 있다({src.loc(pos)})')
        if '원심' in q:
            flags.append("quote 안에 '원심' 낱말이 있다")
        s0, s1 = src.sentence_at(pos)
        sent = body[s0:s1]
        if LOWER_START.match(sent):
            flags.append(f"quote가 든 문장이 '원심은…'으로 시작한다: {norm(sent)[:50]}")
        else:
            p0, p1 = src.para_at(pos)
            lead = body[p0:pos]
            if LOWER_START.match(lead) and not re.search(r'그러나|그런데|하지만|살피건대|살펴보면|기록에 의하면|대법원|당원', lead):
                flags.append(f"quote가 '원심은…'으로 시작하는 문단 안에 있고 그 사이에 돌아서는 말이 없다: {norm(lead)[:50]}")
        hd = src.heading_before(pos)
        if hd and len(hd) <= 30 and LOWER_HEAD.search(hd) and not re.search(r'그러나|수긍|정당|잘못|위법|대법원', hd):
            flags.append(f"quote 위의 머리가 원심 판단을 옮기는 절이다: '{hd[:40]}'")
        ns = norm(sent)
        if re.search(r'주장(한다|하였다|하고 있다)\.?$', ns) or re.match(r'^.{0,12}(상고이유(의 요지)?는|논지는|소론은)', ns):
            flags.append(f'quote가 든 문장이 당사자 주장을 옮기는 문장으로 보인다: …{ns[-40:]}')
        if flags:
            for fl in flags:
                R(cid, C(f'rule_parts[{i}]'), 'rule_parts', '원심 문단 표시', CAND, f'{fl} [{src.loc(pos)}]')
        else:
            okc(cid, '원심 문단 표시')
        after = body[src.span(q)[1]: src.span(q)[1] + 250]
        m = re.match(r'^[^.]{0,120}?[,.]\s*(다만|단,|그러나 [^.]{0,40}(특별한 사정|예외))', after)
        cardtext = (c.get('rule') or '') + ' '.join(x.get('quote') or '' for x in c.get('rule_parts') or [])
        m = m if m and after[:m.start(1)].count('다.') == 0 else None
        if m and not re.search(r'다만|그러나|하지만|예외|단서', (c.get('rule') or '')) and sq(after[m.start(1):m.start(1) + 30]) not in sq(cardtext):
            R(cid, C('omit'), 'omit', '잘린 단서', CAND, f"rule_parts[{i}] quote 바로 뒤에 단서가 이어지는데 rule에 단서 말이 없다: …{norm(after[:140])}")
        else:
            okc(cid, '잘린 단서')

    # --- 요지 번호(holding)
    if not src.has_headnote:
        ctx.skip(cid, '요지 번호', '원문 기록에 headnote 칸이 없다(--headnotes)')
    else:
        keys = list(src.si) or list(src.yo)
        if keys and hold not in keys and hold not in src.yo:
            R(cid, C('holding'), 'holding', '요지 번호', CAND, f'카드의 요지 번호 {hold}가 판시사항 번호({", ".join(keys)})에 없다')
        if not src.yo:
            ctx.skip(cid, '요지 번호', '판결요지 칸이 비어 quote와 대조하지 못했다(판시사항만 있다)')
        else:
            for i, q, pos in quotes:
                qf = fz(q)
                sc = {k: fuzzy(qf, v) for k, v in src.yo_fz.items()}
                best = max(sc, key=sc.get)
                if sc[best] < 0.85:
                    ctx.skip(cid, '요지 번호', f'rule_parts[{i}] quote가 어느 요지와도 0.85 미만이다(본문에서만 딴 구절, 최고 [{best}] {sc[best]:.2f})')
                elif best == hold or sc.get(hold, 0) >= 0.85:
                    R(cid, C(f'rule_parts[{i}]'), 'holding', '요지 번호', OK, f'quote가 판결요지 [{hold}]과 글 일치도 {sc.get(hold, 0):.2f}')
                else:
                    R(cid, C(f'rule_parts[{i}]'), 'holding', '요지 번호', CAND,
                      f'quote가 판결요지 [{best}]에 붙는다(글 일치도 {sc[best]:.2f}). 카드의 요지 번호 [{hold}]과는 {sc.get(hold, 0):.2f}다. 다른 요지를 섞었는지 본다')
            # 한정어: rule ↔ 판결요지 [holding]
            yo = src.yo.get(hold)
            if yo:
                a, b = quals(yo), quals(c.get('rule'))
                if a - b:
                    R(cid, C('rule'), 'rule', '한정어(요지에만)', CAND, f"판결요지 [{hold}]에 있고 rule에 없는 한정어: {', '.join(sorted(a - b))}")
                if b - a:
                    R(cid, C('rule'), 'rule', '한정어(rule에만)', CAND, f"rule에 있고 판결요지 [{hold}]에 없는 한정어: {', '.join(sorted(b - a))}")
                if not (a ^ b):
                    okc(cid, '한정어(요지)')
    # 한정어: rule ↔ quote(본문 구절)
    qall = ' '.join(q for _, q, _ in quotes)
    if qall:
        a, b = quals(qall), quals(c.get('rule'))
        if a - b:
            R(cid, C('rule'), 'rule', '한정어(quote에만)', CAND, f"quote에 있고 rule에 없는 한정어: {', '.join(sorted(a - b))}")
        if b - a:
            R(cid, C('rule'), 'rule', '한정어(rule에만, quote 대조)', CAND, f"rule에 있고 quote에 없는 한정어: {', '.join(sorted(b - a))}")
        etc = []
        for m in re.finditer(r'([가-힣]{2,8})\s?등(?=[\s,을를이가의에은는과와으로])', qall):
            w = stem(m.group(1))
            if w in (c.get('rule') or '') and not re.search(re.escape(w) + r'[가-힣]{0,2}\s?(등|따위|같은|같이|처럼)', c.get('rule') or ''):
                etc.append(m.group(0).strip())
        if etc:
            R(cid, C('rule'), 'rule', '한정어(quote에만)', CAND, f"quote의 '…등'이 rule에서 빠졌다: {', '.join(dict.fromkeys(etc))}")
        if not (a ^ b) and not etc:
            okc(cid, '한정어(quote)')

    # --- 낱말 차집합, 날짜·금액
    bvals = {v for v, _ in won_values(body)}
    for tail, field, text in claims_of(c):
        if field not in ('rule', 'result', 'facts', 'cue') or not text:
            continue
        miss = words_missing(text, src.bsq)
        if miss:
            R(cid, C(tail), field, '낱말 차집합', CAND, f"원문에 없는 낱말: {', '.join(miss[:10])}. 문장: {text[:70]}")
        else:
            okc(cid, f'낱말 차집합({field})')
        if field == 'rule':
            continue
        bad = []
        for m in DATE.finditer(text):
            y, mo, d = m.group(1), m.group(2), m.group(3)
            pat = y + r'\s*\.\s*0?' + mo + r'\s*\.' + (r'\s*0?' + d + r'(?!\d)' if d else '')
            if re.search(pat, body):
                continue
            rel = r'(같은 해|동년|그 해|같은 달|동월)\s*0?' + mo + r'\s*\.' + (r'\s*0?' + d + r'(?!\d)' if d else '')
            if d and re.search(rel, body) and y in body:
                continue
            bad.append(m.group(0).strip())
        for m in re.finditer(r'(?<!\d)((?:19|20)\d{2})년', text):
            if m.group(1) not in body:
                bad.append(m.group(0))
        for v, raw in won_values(text):
            if v and v not in bvals:
                bad.append(raw)
        if bad:
            R(cid, C(tail), field, '날짜·금액', CAND, f"원문에 없는 날짜·금액: {', '.join(dict.fromkeys(bad))}. 글: {text[:70]}")
        else:
            okc(cid, '날짜·금액')

    # --- 따옴표
    for tail, field, text in claims_of(c):
        if field not in ('cue', 'facts', 'rule', 'result', 'turn', 'not_decided', 'scope', 'bar_extra') or not text or tail == 'bar_extra.kind':
            continue
        for m in QUOTED.finditer(text):
            span = next(g for g in m.groups() if g)
            if sq(span) in src.bsq:
                okc(cid, '따옴표')
                continue
            others = [n for n in dict.fromkeys(x.group(1) for x in NO.finditer(text)) if n != no]
            if field == 'turn':
                others += [text.rsplit('(', 1)[-1].split('#')[0]]
            where = [n for n in others if n in ctx.srcs and sq(span) in ctx.srcs[n].bsq]
            law = None
            if not where and ctx.law_text is not None:
                for a in ART_IN_TEXT.finditer(text):
                    t = ctx.law_text(a.group(1).strip(), a.group(2) + (f'의{a.group(3)}' if a.group(3) else ''))
                    if t and sq(span) in sq(t):
                        law = f'{a.group(1).strip()} 제{a.group(2)}조'
            if where:
                R(cid, C(tail), field, '따옴표', OK, f"'{span[:40]}'은 이 판결이 아니라 글에 적힌 {where[0]}의 본문에 있다")
            elif law:
                R(cid, C(tail), field, '따옴표', OK, f"'{span[:40]}'은 글에 적힌 {law}의 문언에 있다")
            else:
                R(cid, C(tail), field, '따옴표', CAND,
                  f"따옴표 구절 '{span[:60]}'이 이 판결 본문에 글자 그대로 없다" + (f'(글에 적힌 {", ".join(others)}의 본문에도 없다)' if [n for n in others if n in ctx.srcs] else '')
                  + '. 원문 구절로 바꾸거나 따옴표를 뗀다')

    # --- 참조조문
    refs = norm(src.refs_articles)
    if not refs:
        ctx.skip(cid, '참조조문', '이 판결에 참조조문 칸이 비었다')
    else:
        byn = split_n(src.refs_articles)
        mine_refs = byn.get(hold, refs if list(byn) == ['1'] else '')
        for i, x in enumerate(c.get('articles') or []):
            jo = str(x.get('jo'))
            pat = re.compile(r'제\s*' + re.escape(jo.split('의')[0]) + r'\s*조' + (r'\s*의\s*' + jo.split('의')[1] + r'(?!\d)' if '의' in jo else r'(?!\s*의\s*\d)'))
            if pat.search(mine_refs):
                R(cid, C(f'articles[{i}].role'), 'articles', '참조조문', OK, f"{x.get('law')} 제{jo}조가 이 요지의 참조조문에 있다")
            elif pat.search(refs):
                R(cid, C(f'articles[{i}].role'), 'articles', '참조조문', CAND, f"{x.get('law')} 제{jo}조({x.get('role')})가 이 판결의 다른 요지 참조조문에만 있다(요지 [{hold}]에는 없다)")
            else:
                R(cid, C(f'articles[{i}].role'), 'articles', '참조조문', CAND, f"{x.get('law')} 제{jo}조({x.get('role')})가 이 판결의 참조조문에 없다")

    # --- 공보
    g = case.get('gazette')
    got = ctx.gazette.get(no) or {}
    two = {k: v for k, v in got.items() if len(v) >= 2}
    gk = re.sub(r'[\s,]', '', g or '')
    if g and got:
        if gk in got:
            R(cid, C('case.gazette'), 'case', '공보', OK, f'다른 판결 {len(got[gk])}곳의 참조판례 표기와 같다')
        else:
            R(cid, C('case.gazette'), 'case', '공보', CAND, f"카드 '{g}'가 다른 판결의 참조판례 표기와 다르다: " + ', '.join(f"{ctx.gazette_raw.get((no, k), k)}({len(v)}곳)" for k, v in got.items()))
    elif not g and two:
        k = max(two, key=lambda x: len(two[x]))
        if len(got) == 1:
            R(cid, C('case.gazette'), 'case', '공보', CAND, f"gazette가 비었는데 다른 판결 {len(two[k])}곳({', '.join(sorted(two[k])[:3])})이 '{ctx.gazette_raw.get((no, k), k)}'로 적는다. 두 곳이 같으니 채울 후보다")
        else:
            R(cid, C('case.gazette'), 'case', '공보', CAND, 'gazette가 비었고 다른 판결들의 표기가 서로 다르다: ' + ', '.join(f"{ctx.gazette_raw.get((no, k), k)}({len(v)}곳)" for k, v in got.items()))
    else:
        ctx.skip(cid, '공보', '카드에도 없고 두 곳에서 건진 표기도 없다' if not g else '카드에 있으나 다른 판결에서 건진 표기가 없어 대조하지 못했다')

    # --- bar_extra와 구역표
    kinds = [o['kind'] for o in src.opinions]
    has_minor = [o for o in src.opinions if o['kind'] in ('반대의견', '별개의견')]
    if bx:
        k = bx.get('kind')
        text = bx.get('text') or ''
        hit = False
        if k in ('반대의견', '별개의견'):
            zs = [o for o in src.opinions if o['kind'] == k]
            if not zs:
                R(cid, C('bar_extra.kind'), 'bar_extra', 'bar_extra와 구역표', CAND,
                  f"kind가 {k}인데 본문에 그 이름의 의견 머리가 없다. 구역표의 의견 머리: {'; '.join(o['head'] for o in src.opinions) or '없음'}")
                hit = True
            names = [ws(x) for part in re.findall(r'대법관 ([가-힣 ,]+?)(?=\)|$|의 |이 |은 |는 )', text) for x in part.split(',')]
            names = [n for n in names if 2 <= len(n) <= 4]
            if names and zs and not any(set(names) <= set(o['names']) for o in zs):
                R(cid, C('bar_extra.s0'), 'bar_extra', 'bar_extra와 구역표', CAND,
                  f"text의 대법관 이름({', '.join(names)})이 {k} 머리의 이름과 다르다: {'; '.join(', '.join(o['names']) for o in zs)}")
                hit = True
            for m in re.finditer(r'대법관 (\d+)(?:인|명)', text):
                if zs and not any(len(o['names']) == int(m.group(1)) for o in zs):
                    R(cid, C('bar_extra.s0'), 'bar_extra', 'bar_extra와 구역표', CAND, f"text의 대법관 수({m.group(1)})가 {k} 머리의 수와 다르다: {[len(o['names']) for o in zs]}")
                    hit = True
            zone = ''.join(sq(body[o['start']:o['end']]) for o in zs)
            for m in QUOTED.finditer(text):
                span = next(g for g in m.groups() if g)
                if zs and sq(span) in src.bsq and sq(span) not in zone:
                    R(cid, C('bar_extra.s0'), 'bar_extra', 'bar_extra와 구역표', CAND, f"따옴표 구절 '{span[:40]}'이 {k} 구역이 아니라 다른 구역에 있다")
                    hit = True
            if zs:
                maj = sq(body[src.reason_start:src.maj_end])
                for i, s in enumerate(split_sents(text)):
                    toks = [sm for tk, sm in content_stems(s) if len(sm) >= 3]
                    only_maj = [t for t in toks if t not in zone and t in maj]
                    if toks and len(only_maj) / len(toks) >= 0.3:
                        R(cid, C(f'bar_extra.s{i}'), 'bar_extra', 'bar_extra와 구역표', CAND,
                          f"text 문장 {i}의 낱말 가운데 {k} 구역에 없고 다수의견 구역에만 있는 것이 많다: {', '.join(only_maj[:6])}")
                        hit = True
        elif k == '원심 논리':
            if has_minor:
                R(cid, C('bar_extra.kind'), 'bar_extra', 'bar_extra와 구역표', CAND,
                  f"kind가 원심 논리인데 판결에 반대·별개의견이 있다({'; '.join(o['head'] for o in has_minor)}). 판결 안의 의견이 먼저다")
                hit = True
            if src.flags and src.flags['broken'] == '없음':
                R(cid, C('bar_extra.kind'), 'bar_extra', 'bar_extra와 구역표', CAND, f"kind가 원심 논리(파기된 원심의 논리)인데 주문에 파기가 없다({src.columns[2]})")
                hit = True
        if not hit:
            okc(cid, 'bar_extra와 구역표')
    elif has_minor:
        R(cid, C('bar_extra'), 'bar_extra', 'bar_extra와 구역표', CAND, f"bar_extra가 비었는데 판결에 반대·별개의견이 있다: {'; '.join(o['head'] for o in has_minor)}")
    else:
        okc(cid, 'bar_extra와 구역표')

    # --- 빠뜨림 도움: 결론 문장의 날짜가 facts에 있는가
    card_text = ' '.join([c.get('cue') or '', c.get('result') or ''] + (c.get('facts') or []))
    dates = collections.OrderedDict()
    maj = body[src.reason_start:src.maj_end]
    for m in re.finditer(r'(?:^|(?<=다\.)\s|\n)\s*(?:\(?\d+\)?\s*)?(따라서|그렇다면|그러므로|결국)[^\n]{0,400}?다\.', maj):
        for d in DATE.finditer(m.group(0)):
            if d.group(3):
                dates[(d.group(1), d.group(2), d.group(3))] = norm(m.group(0))[:90]
    miss = [k for k in dates if not re.search(k[0] + r'\s*\.\s*0?' + k[1] + r'\s*\.\s*0?' + k[2] + r'(?!\d)', card_text)]
    if miss and (c.get('facts') or []):
        R(cid, C('omit'), 'omit', '결론 대목의 날짜', CAND,
          f"대법원의 결론 문장(따라서·그렇다면…)에 나온 날짜가 facts·cue·result에 없다: {', '.join('. '.join(k) + '.' for k in miss[:5])}. 결론을 가른 날짜인지 본다")
    else:
        okc(cid, '결론 대목의 날짜')

    # --- not_decided 안내: '요지 n은 카드로 만들지 않았다'
    for i, s in enumerate(split_sents(c.get('not_decided'))):
        for m in re.finditer(r'요지\s*\[?(\d+|[가나다라마바사아자차카타파하](?![가-힣]))\]?', s):
            exists = f'{no}#{m.group(1)}' in ctx.cards
            if exists and re.search(r'카드로 만들지 않|카드가 없|만들지 않았', s):
                R(cid, C(f'not_decided.s{i}'), 'not_decided', 'not_decided 안내', CAND, f'요지 [{m.group(1)}]을 카드로 만들지 않았다고 적었는데 {no}#{m.group(1)} 카드가 있다')
            elif not exists and re.search(r'카드에 있|카드가 맡|#' + re.escape(m.group(1)), s) and m.group(1) != hold:
                R(cid, C(f'not_decided.s{i}'), 'not_decided', 'not_decided 안내', CAND, f'요지 [{m.group(1)}]이 카드에 있다고 적었는데 {no}#{m.group(1)} 카드가 없다: {s[:80]}')


def check_global(ctx, only=None):
    """카드 여럿이나 판결·틀 단위로 보는 검사."""
    R = ctx.row
    cases = {c['case']['no'] for c in ctx.cards.values() if not only or c['id'] in only}
    # asked 거꾸로: 세트 글에는 이 판결이 나오는데 그 판결 카드 어디에도 그 설문이 asked에 없다
    for no in sorted(cases):
        cs = ctx.by_case[no]
        have = {(h.get('exam'), int(h.get('year') or 0), str(h.get('q')), str(h.get('sub') or '')) for c in cs for h in c.get('asked') or []}
        for exam, year, subj, q, sub in sorted(ctx.set_cites.get(no, ())):
            if (exam, year, q, sub) in have or (not sub and any(h[:3] == (exam, year, q) for h in have)):
                continue
            if not sub and any(x[:4] == (exam, year, subj, q) and x[4] for x in ctx.set_cites[no]):
                continue
            R(None, f'판결/{no}', 'asked', 'asked 거꾸로', CAND,
              f"세트 {exam}{year}-{subj}-{q}" + (f' 설문 {sub}' if sub else '') + f"의 글에 {no}이 나오는데 이 판결 카드({', '.join(c['id'] for c in cs)})의 asked에 그 설문이 없다")
    # 비식별: 판결마다 이름 후보
    for no in sorted(cases):
        src = ctx.srcs.get(no)
        if not src:
            continue
        names = src.name_candidates()
        hn = src.rec.get('headnote') or {}
        hn_text = ' '.join(str(hn.get(k) or '') for k in ('판시사항', '판결요지'))
        if names:
            R(None, f'판결/{no}', '비식별', '이름 후보', CAND,
              f"가려지지 않은 개인 이름으로 보이는 낱말 {len(names)}개(역할 낱말 뒤의 성+이름 세 글자 꼴. 이름은 여기 옮기지 않고 성과 자리만 적는다): "
              + ', '.join(f'{k[0]}○○({v}곳, 첫 자리 {src.body.find(k)})' for k, v in names.most_common(8)))
        masks = len(re.findall(r'○○○(?!\d)', src.body))
        if src.rec.get('redacted') and masks >= 2:
            R(None, f'판결/{no}', '비식별', '가림 표지', CAND, f"우리가 가린 '○○○'가 {masks}곳인데 사람마다 다른 표지(○○○1, ○○○2 …)가 아니다. cache 원문으로 다시 가릴 후보(v3.2 레드팀 2)")
        for c in ctx.by_case[no]:
            text = json.dumps({k: c.get(k) for k in ('cue', 'facts', 'rule', 'rule_parts', 'result', 'turn', 'not_decided')}, ensure_ascii=False)
            got = [n for n in names if n in text]
            if got:
                R(c['id'], f"{c['id']}/이름", '비식별', '이름 후보', CAND, f"카드 글에 판결 본문의 이름 후보와 같은 낱말이 있다: {', '.join(n[0] + '○○' for n in got)}")


GROUPS = {'turn': {'turn ref 현행', '같은 판결 turn', '같은 마디·같은 상태 turn', 'turn 이웃 쟁점'},
          'same_rule': {'same_rule 원문', 'same_rule과 turn 겹침', 'same_rule 변경 표기', 'same_rule 방향'},
          '한정어(요지)': {'한정어(요지에만)', '한정어(rule에만)'}, '한정어(quote)': {'한정어(quote에만)', '한정어(rule에만, quote 대조)'},
          'result와 주문': {'result와 주문', "result와 주문('일부'의 두 갈래)", 'slot과 주문'}, '글 속 사건번호 원문': {'글 속 사건번호 원문', '글 속 카드 id', '괄호 속 사건번호 인용'},
          '작업 기록 낱말': {'작업 기록 낱말'}, 'rule 속 주석': {'rule 속 주석'}}


def run_checks(ctx, only=None):
    info = {}
    for cid, c in ctx.cards.items():
        if only and cid not in only:
            continue
        src = ctx.srcs.get(c['case']['no'])
        claims = check_card(ctx, c)
        if src:
            check_case_level(ctx, c, src)
        else:
            ctx.row(cid, f'{cid}/case', 'case', 'case 칸', BAD, f"판결 원문 {c['case']['no']}이 저장소에 없다")
        mine = [r for r in ctx.rows if r['card'] == cid and r['result'] != OK]
        hit = {r['check'] for r in mine} | {f"낱말 차집합({r['field']})" for r in mine if r['check'] == '낱말 차집합'}
        hit |= {g for g, members in GROUPS.items() if any(r['check'] in members for r in mine)}
        ctx.passed[cid] = [x for x in ctx.passed.get(cid, []) if x not in hit]
        cnt = collections.Counter(f for _, f, _ in claims)
        info[cid] = {'claims': dict(cnt), 'claim_ids': [t for t, _, _ in claims], 'hashes': field_hashes(ctx, c, src),
                     'passed': ctx.passed.get(cid, []), 'skipped': ctx.skipped.get(cid, [])}
    check_global(ctx, only)
    return info


def load_law_text(a):
    """조문 문언을 돌려주는 함수. 따옴표 구절의 출처가 조문일 때 쓴다."""
    d = Path(a.laws)
    if not (d / 'index.json').exists():
        return None
    idx = json.loads((d / 'index.json').read_text(encoding='utf-8'))
    docs = {}

    def get(law, jo):
        law = {'헌법': '대한민국헌법'}.get(law, law)
        if law not in idx or law.startswith('_'):
            return None
        if law not in docs:
            docs[law] = json.loads((d / idx[law]['file']).read_text(encoding='utf-8'))
        art = docs[law]['articles'].get(jo)
        return json.dumps(art, ensure_ascii=False) if art else None
    return get


# ---------------------------------------------------------------- 요지 칸 채우기

def add_headnotes(a):
    """cache의 전체 응답에서 판시사항·판결요지·참조조문·참조판례를 headnote 칸으로 옮긴다. 판결 본문(body) 칸은 건드리지 않는다.
    우리가 이름을 가린 판결은 cache 본문과 저장 본문의 차이에서 가린 이름을 찾아 요지 칸에서도 가린다."""
    cache = Path(a.cache)
    done = same = miss = masked = 0
    for p in sorted(Path(a.prec).glob('*.json')):
        rec = json.loads(p.read_text(encoding='utf-8'))
        cp = cache / f"prec-{rec['no']}.json"
        if not cp.exists():
            print(f"{rec['no']}: cache에 전체 응답이 없다(fetch_api.py --full {rec['no']} 로 받는다)")
            miss += 1
            continue
        x = json.loads(cp.read_text(encoding='utf-8')).get('PrecService') or {}
        if str(x.get('판례정보일련번호')) != str(rec.get('serial')):
            print(f"{rec['no']}: cache의 판례일련번호({x.get('판례정보일련번호')})가 저장 기록({rec.get('serial')})과 달라 옮기지 않았다")
            miss += 1
            continue
        hn = {k: html_text(x.get(k)) for k in ('판시사항', '판결요지', '참조조문', '참조판례')}
        if rec.get('redacted'):
            cb = html_text(x.get('판례내용'))
            sm = difflib.SequenceMatcher(None, cb, rec.get('body') or '', autojunk=False)
            names = {cb[i1:i2].strip() for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == 'replace' and '○' in rec['body'][j1:j2]}
            for n in sorted((n for n in names if len(ws(n)) >= 2), key=len, reverse=True):
                for k in hn:
                    if n in hn[k]:
                        hn[k] = hn[k].replace(n, '○○○')
                        masked += 1
        hn['source'] = HEADNOTE_SOURCE
        hn['fetched'] = datetime.date.fromtimestamp(cp.stat().st_mtime).isoformat()
        old = rec.get('headnote')
        if old and {k: old.get(k) for k in ('판시사항', '판결요지', '참조조문', '참조판례')} == {k: hn[k] for k in ('판시사항', '판결요지', '참조조문', '참조판례')}:
            same += 1
            continue
        out = collections.OrderedDict()
        for k, v in rec.items():
            if k == 'body':
                out['headnote'] = hn
            if k != 'headnote':
                out[k] = v
        if 'headnote' not in out:
            out['headnote'] = hn
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        done += 1
    print(f'headnote 칸: 새로 쓰거나 고침 {done}, 그대로 {same}, 못 옮김 {miss}, 요지 칸에서 가린 이름 {masked}곳')
    return 1 if miss else 0


# ---------------------------------------------------------------- 결과 쓰기

def summarize(ctx, info):
    by = collections.defaultdict(collections.Counter)
    for r in ctx.rows:
        by[r['check']][r['result']] += 1
    for cid, x in info.items():
        for ch in x['passed']:
            by[ch]['걸린 것 없음(카드)'] += 1
        for s in x['skipped']:
            by[s['check']]['못 돌림'] += 1
    return {k: dict(v) for k, v in sorted(by.items())}


def scrub(ctx):
    """결과에 옮긴 판결 글에서 이름 후보를 성만 남기고 가린다(가려지지 않은 이름을 결과 파일에 또 싣지 않으려는 것이다)."""
    names = {no: sorted(s.name_candidates(), key=len, reverse=True) for no, s in ctx.srcs.items()}

    def clean(text, no):
        for n in names.get(no, ()):
            text = text.replace(n, n[0] + '○○')
        return text
    for r in ctx.rows:
        no = ctx.cards[r['card']]['case']['no'] if r['card'] in ctx.cards else r['claim'].split('/')[1] if r['claim'].startswith('판결/') else None
        if no and names.get(no):
            r['basis'] = clean(r['basis'], no)
    return clean


def write_out(ctx, info, a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    counts = summarize(ctx, info)
    clean = scrub(ctx)
    sources = {}
    for no in sorted({c['case']['no'] for c in ctx.cards.values()}):
        s = ctx.srcs.get(no)
        if not s:
            continue
        sources[no] = {'serial': s.rec.get('serial'), 'fetched': s.rec.get('fetched'), 'chars': len(s.body), 'order': clean(s.order_text or '', no), 'flags': s.flags,
                       'wording': s.columns[0], 'scope': s.columns[1], 'shown': s.columns[2], 'exception': s.columns[3],
                       'zones': [{'name': f"이유 {x['n']}", 'start': x['start'], 'head': x['head']} for x in s.sections]
                       + [{'name': o['kind'], 'start': o['start'], 'head': o['head'], 'names': o['names']} for o in s.opinions],
                       'majority_end': s.maj_end, 'reversal_sentences': [{**x, 'span': clean(x['span'], no)} for x in s.reversal_sentences()],
                       'headnote': s.has_headnote}
    doc = {'tool': 'pipeline/verify_machine.py', 'guide': GUIDE, 'date': a.date, 'cards': len(info), 'cases': len(sources),
           'results': {'맞음': '기계가 원문과 대조해 확인', '틀림': '기계가 정할 수 있는 규칙을 어김', '후보': '기계가 추림. 사람이 판정한다'},
           'counts': counts, 'rows': ctx.rows, 'card_info': info, 'sources': sources}
    (out / f'machine-{a.date}.json').write_text(dump_lines(doc), encoding='utf-8')
    (out / f'machine-{a.date}.md').write_text(summary_md(ctx, info, counts, sources, a), encoding='utf-8')
    return counts


def dump_lines(doc):
    """json을 쓴다. 결과 줄·카드·판결은 한 줄에 하나씩 써서 파일을 작게 하고 바뀐 곳이 줄 단위로 보이게 한다."""
    j = lambda x: json.dumps(x, ensure_ascii=False, separators=(',', ':'))
    L = ['{']
    for k, v in doc.items():
        if k == 'rows':
            L.append(' "rows":[\n' + ',\n'.join('  ' + j(r) for r in v) + '\n ],')
        elif k in ('card_info', 'sources', 'counts'):
            L.append(f' {j(k)}:{{\n' + ',\n'.join(f'  {j(kk)}:{j(vv)}' for kk, vv in v.items()) + '\n },')
        else:
            L.append(f' {j(k)}:{j(v)},')
    L[-1] = L[-1].rstrip(',')
    return '\n'.join(L) + '\n}\n'


CHECK_NOTES = collections.OrderedDict([
    ('case 칸', '법원·선고일·종류·전합을 원문 기록과 대조(확정)'),
    ('주문', '원문 주문에서 표지 다섯을 읽어 문언 칸·범위 칸을 만들고 disposition과 대조(확정)'),
    ('result와 주문', 'result가 말하는 방향(파기·유지)과 주문의 짝, slot과 주문의 짝'),
    ("result와 주문('일부'의 두 갈래)", "범위 칸이 '일부'인데 result에 한 갈래만 있는 카드"),
    ('slot과 주문', "주문에 파기가 없는데 slot이 '다시 심리(파기환송)'"),
    ('요지 번호', 'quote를 가림·어미 정규화 뒤 판결요지 [n]과 흐리게 대조(0.85). 다른 번호에 붙으면 후보'),
    ('한정어(요지에만)', "판결요지 [holding]에는 있고 rule에는 없는 '원칙적으로·할 수 있다·특별한 사정이 없는 한' 등"),
    ('한정어(rule에만)', 'rule에는 있고 판결요지 [holding]에는 없는 한정어'),
    ('한정어(quote에만)', "quote에는 있고 rule에는 없는 한정어, quote의 '…등'"),
    ('한정어(rule에만, quote 대조)', 'rule에는 있고 quote에는 없는 한정어'),
    ('낱말 차집합', 'rule·result·facts·cue의 문장에만 있고 판결 본문에 없는 내용어'),
    ('날짜·금액', 'result·facts·cue의 날짜·금액이 본문에 있는가(표기 차이는 맞춘다)'),
    ('원심 문단 표시', "quote가 '원심은'으로 시작하는 문장·문단, 원심 판단 절, 주장 문장, 소수의견 구역에 있는가"),
    ('quote 자리', 'quote가 본문에 글자 그대로 있는가(precedent_check와 같은 규칙)'),
    ('참조조문', '카드 articles가 이 요지의 참조조문에 있는가'),
    ('따옴표', '자유 글 속 따옴표 구절이 이 판결 본문(또는 글에 적힌 다른 판결·조문)에 글자 그대로 있는가'),
    ('글 속 사건번호 원문', '카드 글·turn ref·overruled_by의 사건번호가 저장소에 원문이 있는가'),
    ('same_rule 원문', 'same_rule 번호의 원문이 저장소에 있는가'),
    ('괄호 속 사건번호 인용', "'이 판결이 든 ○○'의 번호가 본문·참조판례 칸에 있는가"),
    ('글 속 카드 id', '카드 글에 적힌 카드 id가 있는가'),
    ('turn ref 현행', 'turn이 가리키는 카드가 current false인가'),
    ('같은 마디·같은 상태 turn', 'turn의 ref 카드와 같이 걸린 마디의 상태가 모두 같은가(결론이 같은 후보)'),
    ('같은 판결 turn', 'turn이 같은 판결의 다른 요지를 가리키는가'),
    ('turn 이웃 쟁점', "turn의 result가 '…가 문제 된다'로 끝나는가"),
    ('same_rule 변경 표기', 'same_rule의 판결이 바뀐(일부 바뀐) 판결인가'),
    ('same_rule 방향', 'same_rule 판결의 카드와 같은 마디에서 상태가 반대인가'),
    ('same_rule과 turn 겹침', '같은 번호가 same_rule과 turn에 함께 있는가'),
    ('asked와 원장', 'asked의 설문이 원장에 있는가, 과목이 같은가'),
    ('asked 거꾸로', '세트 글에 이 판결이 나오는데 asked에 그 설문이 없는가'),
    ('세트 basis와 등급', '카드 유사도가 세트 basis의 등급보다 낮은가'),
    ('diff 첫머리', "diff가 '결론 같음/반대'로 시작하는가"),
    ('공보', "다른 판결 참조판례의 '(공…)' 표기와 대조. 비어 있으면 두 곳이 같을 때만 채울 후보"),
    ('bar_extra와 구역표', 'bar_extra의 kind·대법관 이름·수가 의견 머리와 맞는가, 글이 그 의견 구역의 것인가'),
    ('일관성(일부 변경)', 'current false인데 scope가 일부만 바뀌었다고 적는 카드'),
    ('일관성(같은 판결 다른 요지)', '같은 판결의 다른 카드에는 변경 표시가 있는데 이 카드에는 scope가 없음'),
    ('틀 basis 현행', 'current false 카드가 틀 마디 근거로 남아 있는가'),
    ('참조판례 변경 경고', '이 판결이 참조판례로 든 판결의 카드가 current false인가'),
    ('slot과 틀 basis', 'slot이 있으면 그 마디 basis에 카드가 있어야 한다'),
    ('틀 basis에만 있음', 'basis에는 있는데 그 마디 slot이 없는 카드'),
    ('덮음', '카드의 모든 칸이 주장 표에 걸리는가, rule 문장마다 받치는 마디가 있는가'),
    ('cue 쟁점 문장', 'cue가 사실 없이 쟁점 문장뿐인가'),
    ('작업 기록 낱말', '카드 글에 검토자 이름·확인 경위 같은 작업 기록이 있는가'),
    ('rule 속 주석', 'rule에 판례 변경 주석이나 다른 판결 이야기가 있는가'),
    ('닫힌 값', 'found_by 값, searched 유무'),
    ("role '최근' 기한", '최근 카드가 기한(전합 10년, 그 밖 5년)을 넘었는가'),
    ('잘린 단서', 'quote 바로 뒤에 단서가 이어지는데 rule에 단서 말이 없는가'),
    ('결론 대목의 날짜', '대법원의 결론 문장에 나온 날짜가 facts·cue·result에 없는가'),
    ('not_decided 안내', "'요지 n은 카드로 만들지 않았다'와 카드 유무"),
    ('이름 후보', '판결 본문·카드 글의 가려지지 않은 개인 이름 후보(가리지는 않는다)'),
    ('가림 표지', '우리가 가린 이름이 사람마다 다른 표지인가'),
    ('turn 방향', 'turn의 ref 카드와 같이 걸린 마디가 없어 상태를 비교하지 못한 turn(못 돌림으로만 센다)'),
])


def summary_md(ctx, info, counts, sources, a):
    L = [f'# 기계 층 결과 {a.date} (검증 지침서 {GUIDE})', '',
         f'- 도구: `pipeline/verify_machine.py`. 카드 {len(info)}장, 판결 {len(sources)}건, 틀 {len(ctx.frames)}개.',
         '- 맞음은 기계가 원문과 대조해 확인한 것, 틀림은 기계가 정할 수 있는 규칙을 어긴 것, 후보는 사람이 판정할 것이다. 후보가 곧 오류는 아니다.',
         "- '걸린 것 없음'은 그 검사를 그 카드에 돌렸고 후보·틀림이 나오지 않았다는 뜻이다(카드 수). '못 돌림'은 대조할 자료가 없었다는 뜻이다.",
         '- 줄 하나하나는 같은 이름의 json(`rows`)에 있다. 주문 원문과 두 칸, 구역표, 파기 이유 문장, 칸별 해시도 json에 있다.',
         '- 판시사항·판결요지 글은 이 결과에 옮기지 않았다(번호와 글 일치도만 적었다).',
         f"- 공보 표기는 판결 글 {ctx.gazette_texts}건에서 건졌다(저장소 원문 {len(ctx.srcs)}건" + ('' if ctx.a.no_cache or ctx.gazette_texts == len(ctx.srcs) else ', 나머지는 저장소 밖 cache의 전체 응답') + ').',
         '- 결과에 옮긴 판결 글 속 이름 후보는 성만 남기고 가렸다.', '',
         '## 검사별 수', '', '| 검사 | 맞음 | 후보 | 틀림 | 걸린 것 없음 | 못 돌림 | 무엇을 보나 |', '|---|---|---|---|---|---|---|']
    order = list(CHECK_NOTES) + [k for k in counts if k not in CHECK_NOTES and not re.match(r'낱말 차집합\(|한정어\((요지|quote)\)$|turn$|same_rule$|따옴표$', k)]
    alias = {'낱말 차집합': ['낱말 차집합(rule)', '낱말 차집합(result)', '낱말 차집합(facts)', '낱말 차집합(cue)'], '한정어(요지에만)': ['한정어(요지)'],
             '한정어(quote에만)': ['한정어(quote)'], 'turn ref 현행': ['turn'], 'same_rule 원문': ['same_rule']}
    tot = collections.Counter()
    for k in order:
        v = dict(counts.get(k, {}))
        clean = v.get('걸린 것 없음(카드)', 0) + sum(counts.get(x, {}).get('걸린 것 없음(카드)', 0) for x in alias.get(k, []))
        if not v and not clean:
            continue
        for r in (OK, CAND, BAD):
            tot[r] += v.get(r, 0)
        L.append(f"| {k} | {v.get(OK, 0) or ''} | {v.get(CAND, 0) or ''} | {v.get(BAD, 0) or ''} | {clean or ''} | {v.get('못 돌림', 0) or ''} | {CHECK_NOTES.get(k, '')} |")
    L += [f'| **모두** | {tot[OK]} | {tot[CAND]} | {tot[BAD]} | | | |', '',
          "- 낱말 차집합의 '걸린 것 없음'은 칸(rule·result·facts·cue)마다 센 수의 합이다. turn·same_rule의 '걸린 것 없음'은 그 칸의 모든 기계 검사를 지난 카드 수다.", '']
    L += ['## 틀림(기계가 정한 것)', '']
    for r in ctx.rows:
        if r['result'] == BAD and r['check'] not in ('same_rule 원문',):
            L.append(f"- `{r['claim']}` [{r['check']}] {r['basis']}")
    sr = [r for r in ctx.rows if r['check'] == 'same_rule 원문']
    if sr:
        nos = collections.Counter(re.match(r'^(\S+?)의 원문', r['basis']).group(1) for r in sr)
        L += ['', f"- same_rule 번호 가운데 저장소에 원문이 없는 것: 줄 {len(sr)}, 서로 다른 판결 {len(nos)}건. 받아 와야 쌍 단위 판정을 할 수 있다."]
    disp = collections.Counter(s['shown'] or '그 밖' for s in sources.values())
    L += ['', '## 주문(판결 단위)', '', '| 보이는 표기 | 판결 수 |', '|---|---|'] + [f'| {k} | {v} |' for k, v in disp.most_common()]
    kp = Path(a.known)
    if kp.exists():
        known = json.loads(kp.read_text(encoding='utf-8'))
        L += ['', '## 이미 찾은 어긋남이 걸렸나', '', '사람이 원문을 읽고 찾아 둔 어긋남(`pipeline/tests/verify/known.json`)을 기계가 잡는지 본다. 카드가 고쳐지면 "안 걸림"이 되는 것이 정상이다.', '',
              '| 카드 | 어긋남 | 잡을 검사 | 결과 |', '|---|---|---|---|']
        for k in known:
            hits = [r for r in ctx.rows if (r['card'] == k['card'] or r['claim'].startswith(k['card'])) and r['check'] in k['checks']
                    and r['result'] != OK and (not k.get('match') or k['match'] in r['basis'] or k['match'] in r['claim'])]
            L.append(f"| {k['card']} | {k['what']} | {', '.join(k['checks']) or '(기계로 못 잡는 꼴)'} | "
                     + (f"걸림: {hits[0]['result']}, `{hits[0]['claim'].split('/')[-1]}`" if hits else ('기계 범위 밖' if not k['checks'] else '안 걸림')) + ' |')
    L += ['', '## 만들지 않은 검사', '',
          '- 사건번호 역검색(그 판결을 인용·변경한 뒤 판결 찾기), searched 재현: law.go.kr 호출이 필요해 주기 점검(`pipeline/update_check.py`)에 둔다.',
          '- ev 근거 구절 검사(span이 원문에 있는가, loc 구역 안인가, rule quote와 겹치지 않는가): 카드에 아직 ev 칸이 없다.',
          '- turn의 방향 비교는 두 카드가 같은 틀 마디에 걸려 있을 때만 한다. 같이 걸린 마디가 없는 turn은 못 돌림으로 세었다. 글만으로 결론 방향을 읽는 일은 쌍 단위(사람)에 둔다.',
          '- 낱말 차집합과 이름 후보는 형태소 분석 없이 조사만 떼고 본다. 쉬운 말로 바꿔 쓴 낱말이 섞여 나온다.',
          '- 조문 층(세트) 기계 검사 넷은 이 도구의 범위가 아니다.', '']
    return '\n'.join(L) + '\n'


# ---------------------------------------------------------------- 자기 시험

def run_overlay(base, card, law_text, watch=None, source=None):
    """진짜 카드들 위에 카드 한 장(과 시험용 판결 원문)을 덮고, 그 카드(또는 watch 카드)의 결과 줄을 돌려준다."""
    ctx = Ctx.__new__(Ctx)
    ctx.__dict__.update(base.__dict__)
    ctx.cards = collections.OrderedDict(base.cards)
    ctx.cards[card['id']] = card
    ctx.by_case = collections.defaultdict(list)
    for c in ctx.cards.values():
        ctx.by_case[c['case']['no']].append(c)
    if source:
        ctx.srcs = dict(base.srcs)
        ctx.srcs[source['no']] = Src(source)
    ctx.rows, ctx.passed, ctx.skipped = [], collections.defaultdict(list), collections.defaultdict(list)
    ctx.law_text = law_text
    run_checks(ctx, only={watch or card['id']})
    return ctx.rows


def fixed_copy(fx):
    """틀린 카드에 control(고친 칸)을 덮은 사본. 값이 '__지움__'인 칸은 뺀다."""
    c = {**fx['card'], **fx.get('control', {})}
    return {k: v for k, v in c.items() if v != '__지움__'}


def expect_hit(rows, e):
    return [r for r in rows if r['check'] == e['check'] and r['result'] == e['result']
            and (not e.get('claim') or r['claim'].endswith(e['claim'])) and (not e.get('basis') or e['basis'] in r['basis'])]


def selftest(a):
    """pipeline/tests/verify/cards의 일부러 틀린 카드가 기대한 검사에 걸리는지, 고친 사본(control)에서는 걸리지 않는지 본다.
    시험 카드 한 장의 꼴: {"tool": "verify_machine"|"precedent_check", "what": 무엇을 틀리게 했나, "card": 틀린 카드, "control": {고친 칸}, "expect": [기대 결과],
    "watch": 결과를 볼 다른 카드 id(없으면 이 카드), "source"·"control_source": 시험용 판결 원문(판결 단위 검사)}"""
    d = Path(a.tests)
    fixtures = [json.loads(p.read_text(encoding='utf-8')) | {'_file': p.name} for p in sorted((d / 'cards').glob('*.json'))]
    a.no_cache = True
    fails, n = [], 0
    law_text = load_law_text(a)
    base = Ctx(a)
    for fx in [f for f in fixtures if f['tool'] == 'verify_machine']:
        n += 1
        bad = run_overlay(base, fx['card'], law_text, fx.get('watch'), fx.get('source'))
        good = run_overlay(base, fixed_copy(fx), law_text, fx.get('watch'), fx.get('control_source') or fx.get('source'))
        for e in fx['expect']:
            if not expect_hit(bad, e):
                fails.append(f"{fx['_file']}: [{e['check']}] {e['result']}이 걸리지 않았다 ({fx['what']})")
            elif expect_hit(good, e):
                fails.append(f"{fx['_file']}: [{e['check']}]가 고친 사본에서도 걸린다(검사가 늘 걸리는 것일 수 있다)")
    # precedent_check.py의 검사: 진짜 카드에 틀린 사본을 덮어 임시 폴더를 만들고 돌린다
    pcs = [f for f in fixtures if f['tool'] == 'precedent_check']
    if pcs:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for p in Path(a.cards).glob('*.json'):
                (tmp / p.name).write_bytes(p.read_bytes())
            for fx in pcs:
                (tmp / fx['file']).write_text(json.dumps(fx['card'], ensure_ascii=False), encoding='utf-8')
            r = subprocess.run([sys.executable, '-I', str(ROOT / 'pipeline' / 'precedent_check.py'), '--cards', str(tmp), '--frames', a.frames,
                                '--prec', a.prec, '--laws', a.laws], capture_output=True, text=True)
            lines = r.stdout.splitlines()
            for fx in pcs:
                n += 1
                for e in fx['expect']:
                    if not any(fx['file'] in ln and e in ln for ln in lines):
                        fails.append(f"{fx['_file']}: precedent_check가 '{e}'를 내지 않았다 ({fx['what']})")
            if r.returncode != 1:
                fails.append('precedent_check가 틀린 카드가 있는데도 종료 코드 1로 끝나지 않았다')
    checks = sorted({e['check'] for f in fixtures if f['tool'] == 'verify_machine' for e in f['expect']})
    missing = [k for k in CHECK_NOTES if k not in checks and k != 'turn 방향']   # turn 방향은 '못 돌림'만 세는 줄이다
    for f in fails:
        print('실패:', f)
    print(f'자기 시험: 틀린 카드 {n}장(기계 층 {n - len(pcs)}, precedent_check {len(pcs)}), 시험한 기계 층 검사 {len(checks)}가지, 실패 {len(fails)}')
    if missing:
        print('시험 카드가 없는 검사:', ', '.join(missing))
    return 1 if fails or missing else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cards', default=str(ROOT / 'data' / 'precedents'))
    ap.add_argument('--frames', default=str(ROOT / 'data' / 'frames'))
    ap.add_argument('--prec', default=str(ROOT / 'sources' / 'api' / 'prec'))
    ap.add_argument('--laws', default=str(ROOT / 'sources' / 'api' / 'laws'))
    ap.add_argument('--ledger', default=str(ROOT / 'data' / 'ledger' / 'ledger-v1.json'))
    ap.add_argument('--sets', default=str(ROOT / 'data' / 'sets'))
    ap.add_argument('--cache', default=str(Path.home() / '.cache' / 'lawgoyang-api'), help='저장소 밖 전체 응답 폴더. 요지 칸 채우기와 공보 건지기에 쓴다')
    ap.add_argument('--no-cache', action='store_true', help='공보를 저장소 원문에서만 건진다')
    ap.add_argument('--out', default=str(ROOT / 'data' / 'verify'))
    ap.add_argument('--tests', default=str(ROOT / 'pipeline' / 'tests' / 'verify'))
    ap.add_argument('--known', default=str(ROOT / 'pipeline' / 'tests' / 'verify' / 'known.json'))
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    ap.add_argument('--card', help='이 카드 한 장만 돌려 화면에 보인다')
    ap.add_argument('--headnotes', action='store_true', help='sources/api/prec/*.json에 headnote 칸을 채운다')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.headnotes:
        sys.exit(add_headnotes(a))
    if a.selftest:
        sys.exit(selftest(a))
    ctx = Ctx(a)
    ctx.law_text = load_law_text(a)
    if a.card:
        if a.card not in ctx.cards:
            sys.exit(f'{a.card} 카드가 없다')
        info = run_checks(ctx, only={a.card})
        for r in ctx.rows:
            print(f"{r['result']} [{r['check']}] {r['claim']}: {r['basis']}")
        print('걸린 것 없음:', ', '.join(info[a.card]['passed']))
        for s in info[a.card]['skipped']:
            print('못 돌림:', s['check'], '-', s['why'])
        return
    info = run_checks(ctx)
    counts = write_out(ctx, info, a)
    tot = collections.Counter(r['result'] for r in ctx.rows)
    print(f"카드 {len(info)}장: 맞음 {tot[OK]}, 후보 {tot[CAND]}, 틀림 {tot[BAD]} → {Path(a.out) / ('machine-' + a.date + '.json')}")
    for k, v in counts.items():
        if v.get(CAND) or v.get(BAD):
            print(f"  {k}: 후보 {v.get(CAND, 0)}, 틀림 {v.get(BAD, 0)}")


if __name__ == '__main__':
    main()
