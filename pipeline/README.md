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

```bash
python3 -I pipeline/exams/scourt_fetch.py data_law <빈 폴더>        # 법무사 2차 문제
python3 -I pipeline/exams/scourt_fetch.py data_hang <빈 폴더>       # 법원행정고시 2차 문제
python3 -I pipeline/exams/gosi_list.py <목록.json>                 # 5급 공채 2차 글과 첨부 목록
python3 -I pipeline/exams/gosi_fetch.py <목록.json> <빈 폴더> 2017 2026   # 5급(행정) 첨부 ZIP
python3 -I pipeline/exams/qnet_fetch.py 공인노무사 <빈 폴더> 2017 2026      # 큐넷: 노무사 2차
python3 -I pipeline/exams/qnet_fetch.py 변리사 <빈 폴더> 2017 2026 --skip 선택   # 큐넷: 변리사 2차 필수과목
python3 -I pipeline/exams/qnet_fetch.py 감정평가사 <빈 폴더> 2017 2026      # 큐넷: 감정평가사 2차
python3 -I pipeline/exams/assembly_fetch.py <빈 폴더> 2017 2026            # 국회: 입법고시 2차(PDF판 ZIP)
```

기출 원문을 받는다. 받은 파일은 저장소 밖(영신 아이클라우드 `40 법학/기출원문/`)에 둔다. `--list-only`는 받지 않고 목록만 본다. 글마다 `_index-*.json`이 같이 생긴다.

```bash
swiftc -O pipeline/exams/pdftext.swift -o <저장소 밖 폴더>/pdftext
<저장소 밖 폴더>/pdftext <문제.pdf> --ocr > <저장소 밖 폴더>/<이름>.txt
python3 -I pipeline/exams/court_check.py <txt 폴더>     # 법무사·법원행정고시: 과목별 쪽 바닥글·【문 N】 점검
```

PDF 글자층을 쪽마다 뽑는다. `--ocr`은 글자층이 없는 쪽(스캔본)을 맥 Vision OCR(한국어·영어)로 읽는다. 甲·乙·丙 같은 한자와 숫자를 가끔 잘못 읽으니, OCR 글자에만 기댄 조문 번호는 '확인 필요'로 둔다. 뽑은 글자도 저장소에 넣지 않는다.

배포용 HWP(법무사·법원행정고시 2017~2026, 입법고시 2018·2019)는 맥미니 Polaris Office Editor에서 열어 인쇄 → PDF 메뉴 '웹 수신에 저장'으로 PDF를 만든다. 배포용 보호는 풀지 않는다(WORK_LOG 26.11.11).

```bash
python3 -I pipeline/ledger.py --v1
```

원장 v1을 만든다(`data/ledger/ledger-v1.json`, `sets-v1.json`). v0 매핑 넷에 `research/v1-*-20261111/` 여덟 묶음(일곱 시험)을 더한다. 묶음 폴더에 `review.jsonl`(줄마다 다시 판단한 확신도)과 `corrections.jsonl`(두 검토가 합의한 바꾸기·지우기·더하기)이 있으면 매핑 위에 얹는다. 게임은 아직 v0을 읽는다.

```bash
python3 -I pipeline/fetch_api.py --ledger data/ledger/ledger-v1.json --cache <저장소 밖 폴더> --outdir sources/api/laws
python3 -I pipeline/fetch_api.py --show 민사소송법 451 452
python3 -I pipeline/fetch_api.py --compare sources/web/laws --cache <같은 폴더>
```

law.go.kr Open API로 오늘 시행 중인 조문을 받는다(시행일 법령 `target=eflaw`. 그냥 '현행'은 시행 전 조항이 섞여 온다, PRINCIPLES 2). 키(OC)는 저장소에 두지 않고 `LAW_OC` 환경변수나 `~/.config/lawgoyang/oc`에서 읽는다. 키는 맥미니 IP로 등록했다. 법령 전체 응답은 cache(기본 `~/.cache/lawgoyang-api`)에 두고, `sources/api/laws/`에는 원장 조문만 웹 임시본과 같은 꼴로 쓴다. `index.json`의 `pending`은 공포됐지만 시행 전인 개정판의 [시행일, 공포번호]다. `--show`는 조문 하나를 바로 보여 주고, `--compare`는 웹 임시본과 글자 단위로 대조한다.

## 저장 키

`lawgoyang-progress-v1`(판 진도, 보카고양 progress 꼴), `lawgoyang-stage-v1`(조문별 빈칸 단계 1~4), `lawgoyang-missed-v1`(조문별 틀린 횟수). 기록 옮기기는 숙련도·틀린 횟수를 합칠 때 큰 쪽을 남긴다(보카고양 missed와 같은 합치기라 공용 코드를 고치지 않았다).
