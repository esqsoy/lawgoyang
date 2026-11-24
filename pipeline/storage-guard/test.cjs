'use strict';
// 저장 키 검사기 공통 검사(같이 쓰는 파일). 분가도 그대로 돌린다. 규칙은 지어낸 예로, 실제 페이지는 config.json으로 본다.
const assert=require('node:assert/strict');
const g=require('./check.cjs');
const REG={games:[{game:'가',prefixes:['ga-']},{game:'나',prefixes:['na-']},{game:'다',prefixes:['zz_']}]};
// 장부
assert.deepEqual(g.checkRegistry(REG),[]);
assert.equal(g.checkRegistry({games:[{game:'가',prefixes:['ga-']},{game:'라',prefixes:['ga-common-']}]}).length,1,'앞머리가 다른 게임 앞머리로 시작하면 잡는다');
assert.equal(g.checkRegistry({games:[{game:'가',prefixes:['Ga']}]}).length,1,'구분 기호 없는 앞머리는 잡는다');
// 페이지
const ok=`<script>const K="ga-seoul-v1";localStorage.setItem(K,"1");localStorage.getItem("ga-mode-v1");/* 나는 'na-' 키를 쓴다 */ const tag="heads-v3";</script>`;
assert.deepEqual(g.checkPage(ok,['ga-'],['na-','zz_'],'p'),[],'자기 키·주석 속 언급·버전 표시는 그냥 둔다');
const bad=`<script>localStorage.clear();localStorage.setItem("seoul-v1","x");const L="na-learned-words-v1";sessionStorage.setItem("ga-x","1");navigator.serviceWorker.register("/sw.js");</script>`;
const p=g.checkPage(bad,['ga-'],['na-','zz_'],'p');
assert.ok(p.some(x=>/clear/.test(x)));
assert.ok(p.some(x=>/앞머리 없는 저장 키 'seoul-v1'/.test(x)));
assert.ok(p.some(x=>/다른 게임 키 'na-learned-words-v1'/.test(x)));
assert.ok(p.some(x=>/sessionStorage/.test(x)));
assert.ok(p.some(x=>/serviceWorker/.test(x)));
// 실제 설정: 장부에 이 게임이 있고 대상 HTML이 규칙을 지킨다
assert.deepEqual(g.run(),[],'이 저장소 페이지가 저장 키 규칙을 지킨다');
console.log('storage-guard: rules OK, pages OK');
