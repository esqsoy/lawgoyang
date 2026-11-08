# 법학고양 파이프라인

원본과 생성물을 나눈다. 생성물(`proto.html`)은 손으로 고치지 않는다.

| 원본 | 무엇 |
|---|---|
| `data/ledger/` | 기출 조문 원장 v0(`pipeline/ledger.py`가 `research/` 매핑 넷에서 만든다): 외울 조문·보관함·세트 목록 |
| `data/sets/*.json` | 기출 세트 카드(세트 = 기출 한 문). 쓰는 기준은 [data/sets/README](../data/sets/README.md) |
| `sources/web/laws/` | 원장 조문 원문(법령마다 한 파일, `index.json` 목록, `_missing`은 못 찾은 법령) |
| `data/proto-cards.json` | 시제품 카드: 사례·설문·답안·인용할 조문(법·조·항·본문/단서)·첫 문구(3단계 빈칸 끝)·해설. 지금은 Claude가 쓴 임시 사례(기출 아님) |
| `data/near.json` | '뜻은 맞음' 짝. 사람이 확인한 것만(설계안 D) |
| `sources/web/*.json` | 조문 원문. API 키 전이라 law.go.kr 웹 화면 두 곳을 대조해 받은 임시본([PRINCIPLES 2](../PRINCIPLES.md#2-조문-원문은-정확하게)) |
| `pipeline/game.html` | 게임 화면·조작 |
| `pipeline/judge.js` | 판정 핵심(어절 단위 줄 맞춤, 인용·일부인용·기각·각하, 앞에서부터 비우는 빈칸 사다리, 헷갈림 알림) |
| `pipeline/record-transfer.js` | 기록 옮기기 공용 코드(탄고고양 사본에서 그대로 떼어 옴, 고치지 않음) |
| `pipeline/comment-widget.js` | 직검수 페이지 줄 댓글 |

## 명령

```bash
python3 -I pipeline/fetch_web.py --law 민법 --lsi 284415 --ef 20260317 --jo 750 756 763 393 394 396 399 --cache <빈 폴더> --out sources/web/minbeop-20260317.json
```

조문 원문을 받는다. 전체 법령 화면과 조문 하나 화면을 따로 받아 한 글자라도 다르면 멈춘다. 받은 HTML은 저장소 밖 폴더에 둔다.

```bash
python3 -I pipeline/ledger.py
```

원장 v0을 다시 만든다.

```bash
python3 -I pipeline/fetch_web.py --ledger data/ledger/ledger-v0.json --cache <빈 폴더> --outdir sources/web/laws
```

원장의 외울 조문을 법령별로 다 받는다(받아 둔 화면은 cache에 남아 다시 돌리면 빠르다).

```bash
python3 -I pipeline/build.py --artifact <미리보기 파일>
```

`proto.html`을 만든다. `--artifact`는 claude.ai 미리보기용 본문만 따로 쓴다(내려받기가 막혀 기록 옮기기 단추는 뺀다).

```bash
python3 -I pipeline/tests/shape_test.py   # 조문 원문 나누기(목 아래 세목 1)~3))
node pipeline/tests/judge.test.cjs
```

판정 검사(17개).

```bash
node pipeline/tests/smoke.cjs proto.html
```

브라우저로 한 판을 돈다: 인용 → 오답과 틀린 어절만 따라쓰기 → 각하 → 결과·숙련도 저장 → 한 판 더(빈칸 2단계, 번호 + 첫 단어). Playwright가 필요하다.

```bash
python3 -I pipeline/review-page.py --out <파일>
```

영신 직검수 페이지. Artifact로 올릴 때 `capabilities: {comments: {}}`. `--sets id,id`로 세트를 고를 수 있다.

```bash
node pipeline/tests/sets.cjs proto.html
```

모든 세트를 브라우저로 한 판씩 돈다(그 단계 정답을 쳐서 인용, 페이지 오류·가로 넘침 검사).

세트 하나만 조립 검사: `python3 -I pipeline/build.py --check --only <세트 id,…>`(파일을 쓰지 않는다).

## 저장 키

`lawgoyang-progress-v1`(판 진도, 보카고양 progress 꼴), `lawgoyang-stage-v1`(조문별 빈칸 단계 1~4), `lawgoyang-missed-v1`(조문별 틀린 횟수). 기록 옮기기는 숙련도·틀린 횟수를 합칠 때 큰 쪽을 남긴다(보카고양 missed와 같은 합치기라 공용 코드를 고치지 않았다).
