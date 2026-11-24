# 공통 기능 표 (분가 쪽)

고양 시리즈 단어장은 공통 기능을 본가(보카고양)에서 만들고 분가가 가져간다. 규칙은 보카고양 `SHARED.md`에 있다. 법학고양은 단어장이 아니어서 가져오는 것을 [PRINCIPLES 0-1](PRINCIPLES.md#0-1-단어장에서-가져오는-것) 표로 좁혀 두었다. 이 파일은 그중 **공통 기능 폴더를 가져온 것**의 버전만 적는다.

- 같이 쓰는 파일은 여기서 고치지 않는다. 고칠 일이 있으면 본가에 요청한다.
- 본가 버전이 '가져간 버전'과 다르면 업데이트가 밀린 것이다. 본가 SHARED.md 표를 보고 다시 가져온다.

| 기능 | 이 저장소 자리 | 가져온 곳 | 가져간 버전 | 본가 버전(본 날) |
|---|---|---|---|---|
| 기록 옮기기 | `pipeline/record-transfer.js`(한 파일 사본), 설정은 `build.py`의 `RT_CONFIG` | 탄고고양 index.html의 RECORD_TRANSFER 구간 | 탄고고양 `f652afe`(26.11.07) | 보카고양 `64d6d0e`(26.11.12. 그 뒤 폴더 `pipeline/record-transfer/`로 나뉨. 화면 동작은 `69e8d5e`와 같다고 적혀 있음. 26.11.24 확인) |
| 저장 키 검사 | `pipeline/storage-guard/`(check.cjs·test.cjs·registry.json·README는 그대로, config.json만 이 저장소 값) | 보카고양 `pipeline/storage-guard/` | 보카고양 `a35dfbd`(26.11.18 사본. 이 폴더의 마지막 변경) | 같음(26.11.24) |

## 확인한 것과 못 한 것 (26.11.24)

- **저장 키 검사.** 이 맥(맥미니)에는 node가 없어 `node pipeline/storage-guard/check.cjs`를 돌리지 못했다. 대신 같은 규칙을 파이썬으로 훑었다.
  - 대상: `proto.html`, `pipeline/game.html`, `pipeline/record-transfer.js`
  - 저장 키는 모두 `lawgoyang-` 앞머리였다(`lawgoyang-progress-v1`, `-stage-v1`, `-missed-v1`, `-filter-v1`).
  - 금지 목록(`localStorage.clear()`, sessionStorage, IndexedDB, 서비스 워커, 쿠키 쓰기)은 없었다.
  - node가 있는 기기에서 검사기를 한 번 돌려야 한다.
- **기록 옮기기.** 본가가 한 파일에서 폴더(`merge.js`·`runtime.js`·`ui.html` 등)로 나뉜 뒤의 차이를 아직 대조하지 않았다.
