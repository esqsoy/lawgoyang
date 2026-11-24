# 법학고양 파이프라인

원본과 생성물을 나눈다. 생성물(`proto.html`)은 손으로 고치지 않는다.

| 원본 | 무엇 |
|---|---|
| `data/ledger/` | 기출 조문 원장 v0·v1(`pipeline/ledger.py`가 `research/` 매핑에서 만든다): 외울 조문·보관함·세트 목록. 게임은 v1을 읽는다(없으면 v0) |
| `data/sets/*.json` | 기출 세트 카드(세트 = 기출 한 문). 쓰는 기준은 [data/sets/README](../data/sets/README.md) |
| `sources/web/laws/` | 원장 조문 원문(법령마다 한 파일, `index.json` 목록, `_missing`은 못 찾은 법령) |
| `data/proto-cards.json` | 시제품 카드: 사례·설문·답안·인용할 조문(법·조·항·본문/단서)·첫 문구(3단계 빈칸 끝)·해설. 지금은 Claude가 쓴 임시 사례(기출 아님) |
| `data/near.json` | '뜻은 맞음' 짝. 사람이 확인한 것만(설계안 D) |
| `sources/web/*.json` | 조문 원문. API 키 전이라 law.go.kr 웹 화면 두 곳을 대조해 받은 임시본([PRINCIPLES 2](../PRINCIPLES.md#2-조문-원문은-정확하게)) |
| `sources/api/laws/` | law.go.kr Open API로 받은 오늘 시행 중인 원장 조문(웹 임시본과 같은 꼴). 웹 임시본에 없는 법령·조문은 빌드가 여기서 채운다 |
| `data/updates/` | 주기 업데이트 점검 보고(`pipeline/update_check.py`). `last.json`은 다음 점검의 시작점 |
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

영신 직검수 페이지. Artifact로 올릴 때 `capabilities: {comments: {}}`. `--sets id,id`로 세트를 고르고 `--title`로 제목을 바꿀 수 있다(머리 숫자는 고른 세트만 센다).

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

- `--force`: 글자층이 있어도 모든 쪽을 OCR한다. 글자층이 깨진 책에 쓴다.
- `--from N --to M`: 그 쪽 범위만 낸다. 첫 줄 `PAGES n`은 늘 나온다.
- 수백 쪽 넘는 스캔본은 한 번에 돌리면 메모리가 1GB 넘게 불어 도중에 죽는다(26.11.24, 8GB 맥미니). 50쪽씩 끊어 돌리고, 마지막 쪽 머리(`=== PAGE n`)로 이어 간다.
- `--ocr` 없이 스캔본을 돌리면 모든 쪽이 `empty`로 나온다. 완성 판정은 쪽 수와 빈 쪽 비율로 같이 본다.

배포용 HWP(법무사·법원행정고시 2017~2026, 입법고시 2018·2019)는 맥미니 Polaris Office Editor에서 열어 인쇄 → PDF 메뉴 '웹 수신에 저장'으로 PDF를 만든다. 배포용 보호는 풀지 않는다(WORK_LOG 26.11.11).

```bash
python3 -I pipeline/ledger.py --v1
```

원장 v1을 만든다(`data/ledger/ledger-v1.json`, `sets-v1.json`). v0 매핑 넷에 `research/v1-*-20261111/` 여덟 묶음(일곱 시험)을 더한다. 묶음 폴더에 `review.jsonl`(줄마다 다시 판단한 확신도·역할)과 `corrections.jsonl`(두 검토가 합의한 바꾸기·지우기·더하기)이 있으면 매핑 위에 얹는다. 역할(`role`: 핵심·보조·제외)은 [PRINCIPLES 1-3](../PRINCIPLES.md)을 따른다. `제외` 줄은 외울 조문에서 빼고 `excluded`에 이유와 함께 남긴다. 조문마다 `years`(핵심+보조, 화면 빈출도)와 `core`(핵심으로 나온 해)를 둔다. 게임은 v1을 읽는다(시험별 빈출도 칩).

```bash
python3 -I pipeline/fetch_api.py --ledger data/ledger/ledger-v1.json --cache <저장소 밖 폴더> --outdir sources/api/laws
python3 -I pipeline/fetch_api.py --show 민사소송법 451 452
python3 -I pipeline/fetch_api.py --compare sources/web/laws --cache <같은 폴더>
```

law.go.kr Open API로 오늘 시행 중인 조문을 받는다(시행일 법령 `target=eflaw`. 그냥 '현행'은 시행 전 조항이 섞여 온다, PRINCIPLES 2). 키(OC)는 저장소에 두지 않고 `LAW_OC` 환경변수나 `~/.config/lawgoyang/oc`에서 읽는다. 키는 맥미니 IP로 등록했다. 법령 전체 응답은 cache(기본 `~/.cache/lawgoyang-api`)에 두고, `sources/api/laws/`에는 원장 조문과 세트 카드가 인용한 조문을 웹 임시본과 같은 꼴로 쓴다(같은 판·같은 글이면 처음 받은 날을 그대로 둔다). `index.json`의 `pending`은 공포됐지만 시행 전인 개정판의 [시행일, 공포번호, 법령일련번호]다(시행예정 판은 일련번호+시행일로만 받힌다). `--show`는 조문 하나를 바로 보여 주고, `--compare`는 웹 임시본과 글자 단위로 대조한다. `--case 2019다12345 …`는 판결(대법원)·결정(헌재) 원문의 판시사항·요지·참조조문·주문을 보여 준다. 세트의 바탕 판결과 카드 판결은 여기서 확인한 것만 적는다.

```bash
python3 -I pipeline/update_check.py                    # 지난 점검(data/updates/last.json)부터 오늘까지
python3 -I pipeline/update_check.py --since 20260101   # 시작일을 정해서
```

주기 업데이트 점검. 세 가지를 본다. (1) 우리 조문(원장·카드)이 든 법령의 현행 시행일이 `sources/api/laws/index.json`과 달라졌으면 우리 조문 글을 대조한다. (2) 120일(`--ahead`) 안에 시행될 개정판을 받아 우리 조문이 어떻게 바뀌는지 적는다. (3) 기간 안 대법원 전원합의체 판결의 참조조문·'(변경)' 판결과 헌재 위헌·헌법불합치 결정의 심판대상조문을 우리 조문·카드 판결과 맞춘다. 결과는 `data/updates/<날짜>.md`·`.json`. 바뀐 조문은 글자 단위로 바뀐 곳(`[-지금-]{+바뀜+}`), 바뀐 항, 그 항을 인용한 카드가 있는 세트를 적는다. 카드·원장은 고치지 않는다(사람이 보고 고친다). 다만 `build.py`가 마지막 보고(`last.json`)의 시행 예정 개정을 읽어, 바뀌는 항을 인용한 카드에 '○○부터 바뀜' 표시를 단다(PRINCIPLES 2-1: 현행 문언을 외우고 표시만). 한 달에 한 번 돌리는 것을 권한다.

```bash
python3 -I pipeline/fetch_api.py --rule 상속등기          # 대법원 등기예규·재판예규 등 행정규칙 찾기(현행 먼저)
python3 -I pipeline/fetch_api.py --rule-id 2200000108619  # 그 본문
```

서류작성·부동산등기 카드처럼 답이 등기예규로 정해지는 곳은 현행 예규 원문으로 확인한다. 예규는 판결이 아니므로 세트 `basis`·카드 `precedent`가 아니라 해설(`note`)·`research`에 '등기예규 제○호(이름)'로 적는다.

## 저장 키

`lawgoyang-progress-v1`(판 진도, 보카고양 progress 꼴), `lawgoyang-stage-v1`(조문별 빈칸 단계 1~4), `lawgoyang-missed-v1`(조문별 틀린 횟수), `lawgoyang-filter-v1`(홈 시험 거르기, 기기마다 따로·기록 옮기기에 넣지 않음). 홈의 '틀린 조문 다시'는 틀린 적 있고 아직 통빈칸에 못 간 조문을 틀린 횟수 순으로 12장까지 모은 판이다(조문마다 한 장, 진도에는 남기지 않는다). 기록 옮기기는 숙련도·틀린 횟수를 합칠 때 큰 쪽을 남긴다(보카고양 missed와 같은 합치기라 공용 코드를 고치지 않았다).
