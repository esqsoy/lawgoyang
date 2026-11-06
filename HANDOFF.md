# 법학고양 인수인계

갱신: 2026-11-07 KST. 이 문서는 최신 상태로 교체하고, 경위는 [WORK_LOG.md](WORK_LOG.md)에 남긴다.

## 지금 상태

- **설계안 채택(26.11.07 영신 "모두 동의해").** 추천을 모두 채택했고, 5년·10년(A3)만 조사 뒤에 정한다. 요약은 [PRINCIPLES 7-1](PRINCIPLES.md#7-1-설계안-결정), 전문은 [design/proposal-20261107.md](design/proposal-20261107.md). 읽기 페이지 https://claude.ai/artifact/SHQ9mxXn2L1q3AZD68ec1M
- **시제품 있음, 배포 없음.** `proto.html`(생성물) ← [pipeline/](pipeline/README.md). 임시 민법 불법행위 사례 1개, 4장(제750조, 제756조 제1항 본문, 제763조 → 제396조). 사례·답안·해설은 Claude가 쓴 임시 예시(기출 아님). 빈칸 사다리 4단계, 인용·일부인용·기각·각하, 틀린 어절만 따라쓰기, '뜻은 맞음', 헷갈림 알림, 조문 제목 힌트, 첫 글자 힌트, 기록 옮기기(`lawgoyang-`).
  - 미리보기(Artifact, 기록 옮기기 단추 뺀 판): https://claude.ai/artifact/YTs5dJdTDsZhYtLbMY7zUR
  - 영신 직검수 페이지(4장 사례·답안·조문·해설, 줄 댓글): https://claude.ai/artifact/8d7VgGyWzfxw6RYYzmipMz
  - 검사: `node pipeline/tests/judge.test.cjs` 13개, `node pipeline/tests/smoke.cjs proto.html`(Chromium 390px 한 판) 통과(26.11.07). 실제 폰 한글 자판(조합 중 입력)은 미확인.
- **조문 원문은 임시본:** API 키 전이라 law.go.kr 웹 화면 두 곳(lsInfoR·lsSideInfoP)을 대조해 받은 `sources/web/minbeop-20260317.json`(민법 2026. 3. 17. 시행, 법률 제21454호). 키가 오면 API로 다시 받아 대조한다([PRINCIPLES 2](PRINCIPLES.md#2-조문-원문은-정확하게)).
- **조사 중:** 5년·10년 풀 차이(영신 "리서치를 철저하게 선행해줘"). 방법은 설계안 A3.
  - 끝남: 변호사시험 공법 사례형 1~15회 시범([research/gongbeop-pilot-20261107](research/gongbeop-pilot-20261107/README.md)). 10년 창이 20%p 더 덮음(51% → 71%), 외울 양 +33%, 이득은 거의 헌법·헌재법·행소법. '확실'만이면 +15%p.
  - **영신(26.11.07): 5년은 부족. 몇 년으로 할지(8·9·10·11·12…)를 데이터로 정한다**([PRINCIPLES 1](PRINCIPLES.md#1-무엇을-외우나-사례형-기출-조문)). 공법 위험률(마지막 출제 후 g년 된 조문이 다시 나온 비율): 3~10년 13~16%로 평평, 11~12년 4.8%(1/21), 13~14년 8.3%(1/12) — 11년 이상은 표본이 작다.
  - 끝남: 변시 민사법 사례형 시범([research/minsa-pilot-20261107](research/minsa-pilot-20261107/README.md)). 52% → 66%(+13%p), 외울 양 +54%, 6~10년 조문 효율은 5년 풀의 절반.
  - 끝남: 사법시험 2차 공법(2002~2017)을 이어 붙인 분석([research/sasi-gongbeop-20261107](research/sasi-gongbeop-20261107/README.md)). 5~10년 8~9%로 평평, 11년부터 2% 안팎(p≈0.001). 공법은 10년(11·12년은 풀만 커짐, 8년 −8%p).
  - 진행 중: 사법시험 2차 민사(민법·민소, 2003~2017) 이어 붙이기. 끝나면 민사 N과 함께 최종안을 영신에게 낸다.
  - 끝남: 시험별 기출 공개처·이용 조건 조사([research/exam-sources-20261107](research/exam-sources-20261107.md)). 큐넷(노무사·변리사·감정평가사)과 법무부(변시·사시, 26.11.07 영신 브라우저 확인)는 공공누리 1유형 → 출처 달고 기출 사례 원문 사용 가능([PRINCIPLES 4](PRINCIPLES.md#4-저작권)), 입법고시·5급은 표시 없음, 법무사·법원행정고시 미확인. 변시·사시 채점기준 비공개. 사시 마지막 2차는 2017년 제59회.

## 막힌 것

- **law.go.kr Open API 키:** `OC=test` 호출이 "사용자 정보 검증에 실패하였습니다"를 돌려준다(26.11.07). 영신이 open.law.go.kr에서 OPEN API를 신청(OC)하고 맥미니 IP를 등록해야 한다. 이 클라우드 세션은 나가는 IP가 바뀐다(몇 초 사이에 160.79.106.138과 .19).
- **기출 이용 조건:** 법무부·큐넷 1유형 글은 출처를 달고 쓸 수 있다(26.11.07). 법무사·법원행정고시·입법고시·5급은 확인 전이라 원문을 넣지 않는다. 저장소는 공개다.

## 다음 일

1. 영신: 시제품을 폰에서 해 보고, 직검수 페이지에 댓글. 특히 한글 자판 입력이 칸에 제대로 들어가는지.
2. 조사 결과로 5년·10년 비교와 시험별 이용 조건 표를 영신에게 낸다 → 영신이 A3·A2 후보를 정한다.
3. 영신이 API 키를 신청한다 → API로 받는 스크립트, 임시본과 대조.
4. 이용 조건이 확인되면 기출 사례로 첫 진짜 묶음(설계안 시제품 '가': 민법 불법행위).
5. 공개 배포(GitHub Pages)는 영신이 요청하면. 그때 DEPLOYMENT.md를 만든다.

## 작업 환경

- 저장소 esqsoy/lawgoyang(공개). 26.11.07 클라우드 세션에서 시작했다. 세션에 정해진 가지 `claude/vibrant-bell-7w9tsh`로 올렸고, 빈 저장소에 처음 올린 가지라 이 가지가 GitHub 기본 가지가 됐다(`git ls-remote --symref`로 확인). main으로 바꿀지는 영신이 정한다.
- 읽기만 하는 참고 저장소: [tangogoyang](https://github.com/esqsoy/tangogoyang)(PRINCIPLES 1·2-9·10, UI_STANDARD, index.html 기록 옮기기 — `pipeline/record-transfer.js`는 f652afe에서 떼어 옴), [palagoyang](https://github.com/esqsoy/palagoyang) `goyang-common/`(사람 이름 규칙). esqsoy/vocagoyang은 건드리지 않는다.
- 설계안의 원문 예시는 law.go.kr 웹 화면에서 확인했다: 대한민국헌법(lsiSeq 61603, 1988. 2. 25. 시행), 민법(lsiSeq 284415, 2026. 3. 17. 시행, 법률 제21454호), 저작권법(lsiSeq 285693, 2026. 10. 29. 시행, 법률 제21595호).
- 설계안 HTML(`design/proposal-20261107.html`)은 세션 임시 폴더의 생성 스크립트로 만들었다. 고칠 때는 이 파일을 직접 고치고 같은 Artifact 주소에 다시 올린다. 시제품 미리보기·직검수 페이지는 `pipeline/build.py --artifact`, `pipeline/review-page.py --out`으로 다시 만들어 같은 주소에 올린다(주소는 위).
